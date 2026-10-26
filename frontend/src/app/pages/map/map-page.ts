import { HttpClient } from '@angular/common/http';
import {
  
  Component,
  DestroyRef,
  ElementRef,
  afterNextRender,
  computed,
  effect,
  inject,
  input,
  linkedSignal,
  WritableSignal,
  signal,
  untracked,
  viewChild,
} from '@angular/core';
import { Router } from '@angular/router';
import * as L from 'leaflet';
import { firstValueFrom } from 'rxjs';
import type { Agency, AgencyId, Place, Route, ShapeCollection, Vehicle } from '../../api/models';
import { apiUrls } from '../../api/urls';
import { ClockService } from '../../core/clock.service';
import { OperatorService } from '../../core/operator.service';
import { polled } from '../../core/polled';
import { tripLabel, vehicleKey } from '../../lib/agencies';
import { escapeHtml, safeColor, stationName } from '../../lib/format';
import { LegendEntry, legendEntries } from '../../lib/legend';
import { STORAGE_KEYS, readJson, writeJson } from '../../lib/storage';
import { formatAge, formatInstant } from '../../lib/time';
import { StateView } from '../../shared/state';
import { FeedNote } from '../../shell/feed-note';

/** San Francisco and the Peninsula, for before anything has loaded. */
const DEFAULT_CENTER: L.LatLngExpression = [37.6, -122.35];
const DEFAULT_ZOOM = 10;
/** Street stops (as opposed to stations) only show from this zoom in; a zoom earlier with stops on top. */
const STOPS_ZOOM = 14;

/**
 * Which layer is on top and takes taps. Leaflet's line and stop layers each
 * catch taps anywhere over the map, so only the top one can be tapped; the
 * others fade and let taps through.
 */
export type MapTop = 'vehicles' | 'stops' | 'lines';
/** Marker radii: normal, and with stops on top (bigger to see and to tap). */
const RADIUS = { station: [6, 8], stop: [3.5, 5.5] } as const;
const MAP_TOPS: readonly MapTop[] = ['vehicles', 'stops', 'lines'];
const PANE_Z: Record<MapTop, { routes: string; stations: string }> = {
  vehicles: { routes: '400', stations: '450' },
  stops: { routes: '400', stations: '450' },
  // Above the stops, still below the vehicles (markerPane, 600).
  lines: { routes: '500', stations: '450' },
};
/** Shown by default: rail of every kind, and ferries. Bus networks are opt-in. */
const DEFAULT_TYPES = new Set([0, 1, 2, 4, 5, 12]);

/** Routes standing out from the rest: a tapped line, or a legend pick (its key). */
interface Highlight {
  routes: ReadonlySet<string>;
  legend?: string;
}

/** One agency's lines and places, fetched once per visit and kept. */
interface AgencyLayers {
  shapes: L.LayerGroup;
  casing: L.GeoJSON;
  lines: L.GeoJSON;
  stations: L.FeatureGroup;
  stops: L.LayerGroup;
}

const VEHICLE_STATUS: Record<string, string> = {
  incoming_at: 'Arriving',
  stopped_at: 'Stopped',
  in_transit_to: 'In transit',
};

@Component({
  selector: 'app-map-page',
  imports: [StateView, FeedNote],
  templateUrl: './map-page.html',
  styleUrl: './map-page.scss',
})
export class MapPage {
  protected readonly op = inject(OperatorService);
  private readonly router = inject(Router);
  private readonly clock = inject(ClockService);
  private readonly http = inject(HttpClient);

  /** ?vehicle=<vehicleKey> centers on that vehicle once it shows up. */
  readonly vehicle = input<string>();

  private readonly mapEl = viewChild.required<ElementRef<HTMLDivElement>>('map');
  private readonly map = signal<L.Map | null>(null);

  private readonly code = computed(() => (this.op.noFeed() ? undefined : this.op.code()));

  /** Agencies drawn on the map; null until the agency list is known. Starts with whatever was shown last time, else rail. */
  protected readonly selected = linkedSignal<Agency[] | undefined, ReadonlySet<AgencyId> | null>({
    source: () => this.op.agencies.data(),
    computation: (agencies, previous) => previous?.value ?? (agencies ? this.initialAgencies(agencies) : null),
  });
  protected readonly loadingAgencies = signal<ReadonlySet<AgencyId>>(new Set());
  protected readonly failedAgencies = signal<ReadonlySet<AgencyId>>(new Set());

  protected readonly routes = polled<Route[]>(() => {
    const c = this.code();
    return c && apiUrls.routes(c);
  });
  private readonly allVehicles = polled<Vehicle[]>(
    () => {
      const c = this.code();
      return c && apiUrls.vehicles(c);
    },
    { intervalMs: 30_000 },
  );
  protected readonly vehicles = {
    ...this.allVehicles,
    data: computed(() => {
      const list = this.allVehicles.data();
      const sel = this.selected();
      if (!list || !sel) return list;
      return list.filter((v) => !v.route || sel.has(v.route.agency));
    }),
  };

  protected readonly legend = computed(() =>
    legendEntries(this.routes.data() ?? [], this.selected() ?? new Set(), (id) => this.op.agencyName(id)),
  );

  /** Why /vehicles is empty: it's empty both when realtime is stale and when no trains run. */
  protected readonly noVehiclesText = computed(() => {
    const rt = this.op.realtime();
    if (rt.vehiclePositions === 'unavailable') return 'Live train positions are unavailable.';
    if (rt.vehiclePositions === 'stale') {
      const at = this.op.operator()?.realtime.vehicle_positions_at;
      return `Live train positions are delayed${at ? ` — last update ${formatAge(at, this.clock.now())}` : ''}.`;
    }
    return 'No trains are running right now.';
  });

  protected readonly estimatedCount = computed(
    () => (this.vehicles.data() ?? []).filter((v) => v.source === 'estimated').length,
  );

  protected readonly vehiclesUpdated = computed(() => {
    const t = this.vehicles.updatedAt();
    return t ? formatInstant(t, this.op.timeZone()) : '';
  });

  private readonly layers = new Map<AgencyId, AgencyLayers>();
  private readonly fetching = new Set<AgencyId>();
  /** Stops draw on one canvas in their own pane; a wide tolerance makes small dots easy to tap. */
  private readonly renderer = L.canvas({ padding: 0.5, pane: 'stations', tolerance: 6 });
  protected readonly top = signal<MapTop>(this.storedTop());
  private readonly highlighted = signal<Highlight | null>(null);
  /** What's highlighted; a picked line whose agency was turned off is gone from the legend, and so is its pick. */
  private readonly highlight = computed(() => {
    const h = this.highlighted();
    return h?.legend && !this.legend().some((e) => e.key === h.legend) ? null : h;
  });
  protected readonly legendPicked = computed(() => this.highlight()?.legend ?? null);
  private readonly vehicleLayer = L.layerGroup();
  private readonly vehicleMarkers = new Map<string, L.Marker>();
  protected fitted = false;
  private focusedVehicle = '';
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly resizes = new ResizeObserver(() => this.map()?.invalidateSize());

  protected readonly safeColor = safeColor;

  constructor() {
    afterNextRender(() => {
      const m = L.map(this.mapEl().nativeElement, {
        center: DEFAULT_CENTER,
        zoom: DEFAULT_ZOOM,
        zoomControl: true,
        // Fitting between the floating panels shouldn't round down a whole level.
        zoomSnap: 0.25,
        attributionControl: false,
      });
      L.control.attribution({ prefix: false }).addTo(m);
      L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      }).addTo(m);
      // Lines, then stations, then trains (markerPane, 600); "lines on top" lifts the lines.
      m.createPane('routes').style.zIndex = PANE_Z.vehicles.routes;
      m.createPane('stations').style.zIndex = PANE_Z.vehicles.stations;
      this.vehicleLayer.addTo(m);
      m.on('zoomend', () => {
        for (const layers of this.layers.values()) this.updateStops(m, layers);
      });
      m.on('popupclose', () => this.dropTapHighlight());
      this.map.set(m);
      // The container is resized by the layout too (alerts opening, a
      // breakpoint), not just the window, which is all Leaflet watches.
      this.resizes.observe(this.mapEl().nativeElement);
    });

    inject(DestroyRef).onDestroy(() => {
      this.resizes.disconnect();
      this.map()?.remove();
    });

    effect(() => this.syncLayers(this.map(), this.selected()));
    effect(() => this.applyTop(this.map(), this.top()));
    effect(() => this.applyHighlight(this.highlight()));
    effect(() => this.drawVehicles(this.map(), this.vehicles.data()));
    effect(() => this.focusVehicle(this.map(), this.vehicles.data(), this.vehicle()));
  }

  private initialAgencies(agencies: Agency[]): ReadonlySet<AgencyId> {
    const ids = new Set(agencies.map((a) => a.id));
    const stored = readJson<unknown>(STORAGE_KEYS.mapAgencies(this.op.code()), null);
    const remembered = Array.isArray(stored) ? stored.filter((id): id is string => ids.has(id)) : [];
    const shown = agencies.filter((a) => a.route_types.some((t) => DEFAULT_TYPES.has(t))).map((a) => a.id);
    return new Set(remembered.length ? remembered : shown.length ? shown : [...ids]);
  }

  protected readonly failedNames = computed(() =>
    [...this.failedAgencies()].map((id) => this.op.agencyName(id)).join(' and '),
  );

  protected retry(): void {
    this.failedAgencies.set(new Set());
    this.syncLayers(this.map(), this.selected());
  }

  protected readonly tops = MAP_TOPS;

  protected setTop(top: MapTop): void {
    this.top.set(top);
    writeJson(STORAGE_KEYS.mapTop, top);
  }

  private storedTop(): MapTop {
    const v = readJson<unknown>(STORAGE_KEYS.mapTop, 'vehicles');
    return MAP_TOPS.includes(v as MapTop) ? (v as MapTop) : 'vehicles';
  }

  private applyTop(m: L.Map | null, top: MapTop): void {
    if (!m) return;
    m.getPane('routes')!.style.zIndex = PANE_Z[top].routes;
    m.getPane('stations')!.style.zIndex = PANE_Z[top].stations;
    // The fading and tap-through rules are CSS keyed on this (styles.scss).
    m.getContainer().dataset['top'] = top;
    if (top !== 'lines') {
      m.closePopup();
      this.dropTapHighlight();
    }
    for (const layers of this.layers.values()) {
      this.sizeMarkers(layers);
      this.updateStops(m, layers);
    }
  }

  private sizeMarkers(layers: AgencyLayers): void {
    const big = untracked(this.top) === 'stops' ? 1 : 0;
    layers.stations.eachLayer((l) => (l as L.CircleMarker).setRadius(RADIUS.station[big]));
    layers.stops.eachLayer((l) => (l as L.CircleMarker).setRadius(RADIUS.stop[big]));
  }

  /** Fade every line and vehicle but the highlighted routes'. */
  private applyHighlight(h: Highlight | null): void {
    for (const layers of this.layers.values()) {
      layers.lines.eachLayer((l) => {
        const id = ((l as L.Path & { feature?: GeoJSON.Feature }).feature?.properties as { route_id?: string } | undefined)
          ?.route_id;
        (l as L.Path).setStyle({ opacity: !h || (id && h.routes.has(id)) ? 0.95 : 0.15 });
      });
      layers.casing.setStyle({ opacity: h ? 0.15 : 0.5 });
    }
    for (const v of untracked(this.vehicles.data) ?? []) {
      const marker = this.vehicleMarkers.get(vehicleKey(v));
      if (marker) this.fadeVehicle(marker, v, h);
    }
  }

  private fadeVehicle(marker: L.Marker, v: Vehicle, h: Highlight | null): void {
    const lit = !h || (!!v.route && h.routes.has(v.route.id));
    marker.setOpacity(lit ? 1 : 0.2);
    marker.setZIndexOffset(h && lit ? 2000 : 1000);
  }

  /** A tapped line's highlight lasts as long as its popup; a legend pick until unpicked. */
  private dropTapHighlight(): void {
    if (!untracked(this.highlight)?.legend) this.highlighted.set(null);
  }

  protected pickLegend(e: LegendEntry): void {
    const again = this.legendPicked() === e.key;
    this.map()?.closePopup();
    this.highlighted.set(again ? null : { routes: new Set(e.routes), legend: e.key });
  }

  private lineClicked(e: L.LeafletMouseEvent, routeId: string): void {
    const route = this.routes.data()?.find((r) => r.id === routeId);
    const title = route ? route.long_name || route.short_name : routeId;
    const sub = route ? `${this.op.agencyName(route.agency)}${route.long_name && route.short_name ? ` · ${route.short_name}` : ''}` : '';
    this.highlighted.set({ routes: new Set([routeId]) });
    L.popup({ autoPan: false }).setLatLng(e.latlng).setContent(this.popup(title, sub, '', '')).openOn(this.map()!);
  }

  protected toggle(id: AgencyId): void {
    const next = new Set(this.selected() ?? []);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    this.selected.set(next);
    writeJson(STORAGE_KEYS.mapAgencies(this.op.code()), [...next]);
  }

  /** Show the selected agencies' layers, fetching any not loaded yet. */
  private syncLayers(m: L.Map | null, sel: ReadonlySet<AgencyId> | null): void {
    const code = this.code();
    if (!m || !sel || !code) return;
    for (const [id, layers] of this.layers) {
      if (sel.has(id)) this.show(m, layers);
      else this.hide(layers);
    }
    for (const id of sel) {
      if (!this.layers.has(id) && !this.fetching.has(id)) void this.load(m, code, id);
    }
  }

  private async load(m: L.Map, code: string, id: AgencyId): Promise<void> {
    this.fetching.add(id);
    this.mark(this.loadingAgencies, id, true);
    this.mark(this.failedAgencies, id, false);
    try {
      const [shapes, places] = await Promise.all([
        firstValueFrom(this.http.get<ShapeCollection>(apiUrls.shapes(code, { agency: id }))),
        firstValueFrom(this.http.get<Place[]>(apiUrls.stations(code, { agency: id }))),
      ]);
      const layers = { ...this.shapeLayers(shapes), ...this.placeLayers(places) };
      this.layers.set(id, layers);
      this.sizeMarkers(layers);
      if (untracked(this.selected)?.has(id)) this.show(m, layers);
      this.fitOnce(m);
    } catch {
      this.mark(this.failedAgencies, id, true);
    } finally {
      this.fetching.delete(id);
      this.mark(this.loadingAgencies, id, false);
    }
  }

  private mark(set: WritableSignal<ReadonlySet<AgencyId>>, id: AgencyId, on: boolean): void {
    const next = new Set(set());
    if (on) next.add(id);
    else next.delete(id);
    set.set(next);
  }

  private show(m: L.Map, layers: AgencyLayers): void {
    layers.shapes.addTo(m);
    layers.stations.addTo(m);
    this.updateStops(m, layers);
  }

  private hide(layers: AgencyLayers): void {
    layers.shapes.remove();
    layers.stations.remove();
    layers.stops.remove();
  }

  private updateStops(m: L.Map, layers: AgencyLayers): void {
    const from = untracked(this.top) === 'stops' ? STOPS_ZOOM - 1 : STOPS_ZOOM;
    if (m.getZoom() >= from && m.hasLayer(layers.stations)) layers.stops.addTo(m);
    else layers.stops.remove();
  }

  private shapeLayers(fc: ShapeCollection): Pick<AgencyLayers, 'shapes' | 'casing' | 'lines'> {
    // A dark casing under each line keeps pale route colors visible on the basemap.
    const casing = L.geoJSON(fc as GeoJSON.FeatureCollection, {
      style: () => ({ color: '#1b1d1f', weight: 6, opacity: 0.5, lineCap: 'round', lineJoin: 'round' }),
      interactive: false,
      pane: 'routes',
    });
    // Interactive, but only tappable with lines on top: the other modes turn
    // their pointer events off in styles.scss.
    const lines = L.geoJSON(fc as GeoJSON.FeatureCollection, {
      style: (f) => ({
        color: safeColor((f?.properties as { color?: string } | undefined)?.color),
        weight: 3.5,
        opacity: 0.95,
        lineCap: 'round',
        lineJoin: 'round',
      }),
      pane: 'routes',
      onEachFeature: (f, layer) => {
        const routeId = (f.properties as { route_id: string }).route_id;
        layer.on('click', (e) => this.lineClicked(e as L.LeafletMouseEvent, routeId));
      },
    });
    const shapes = L.layerGroup([casing, lines]);
    const h = untracked(this.highlight);
    if (h) queueMicrotask(() => this.applyHighlight(h));
    return { shapes, casing, lines };
  }

  private placeLayers(places: Place[]): Pick<AgencyLayers, 'stations' | 'stops'> {
    const marker = (p: Place, radius: number) =>
      L.circleMarker([p.lat, p.lon], {
        radius,
        color: '#1b1d1f',
        weight: radius > 4 ? 2 : 1.5,
        fillColor: '#ffffff',
        fillOpacity: 1,
        renderer: this.renderer,
      })
        .bindTooltip(stationName(p.name), { direction: 'top', offset: [0, -radius] })
        .bindPopup(() =>
          this.popup(
            stationName(p.name),
            p.routes.map((r) => r.short_name).filter((n, i, all) => all.indexOf(n) === i).slice(0, 8).join(' · '),
            'Departures →',
            `/stations/${encodeURIComponent(p.id)}`,
          ),
        );
    return {
      stations: L.featureGroup(places.filter((p) => p.kind === 'station').map((p) => marker(p, RADIUS.station[0]))),
      stops: L.layerGroup(places.filter((p) => p.kind === 'stop').map((p) => marker(p, RADIUS.stop[0]))),
    };
  }

  /** Frame the first agencies to load, unless a vehicle link is in charge. */
  private fitOnce(m: L.Map): void {
    if (this.fitted || this.vehicle() || this.fetching.size > 1) return;
    const bounds = L.latLngBounds([]);
    for (const layers of this.layers.values()) {
      if (m.hasLayer(layers.stations)) bounds.extend(layers.stations.getBounds());
    }
    if (bounds.isValid()) {
      m.fitBounds(bounds, this.fitPadding());
      this.fitted = true;
    }
  }

  /** Room around the network, clear of the panels floating over the map on large screens. */
  private fitPadding(): L.FitBoundsOptions {
    const host = this.host.nativeElement;
    const map = this.mapEl().nativeElement.getBoundingClientRect();
    const panel = (selector: string) => {
      const el = host.querySelector<HTMLElement>(selector);
      return el && getComputedStyle(el).position === 'absolute' ? el.getBoundingClientRect() : null;
    };
    const top = panel('.controls');
    const bottom = panel('.below');
    return {
      paddingTopLeft: [24, top ? top.bottom - map.top + 12 : 24],
      paddingBottomRight: [24, bottom ? map.bottom - bottom.top + 12 : 24],
    };
  }

  private drawVehicles(m: L.Map | null, list: Vehicle[] | undefined): void {
    if (!m || !list) return;
    const h = untracked(this.highlight);
    const seen = new Set<string>();
    for (const v of list) {
      const key = vehicleKey(v);
      seen.add(key);
      const icon = this.vehicleIcon(v);
      let marker = this.vehicleMarkers.get(key);
      if (marker) {
        marker.setLatLng([v.lat, v.lon]);
        marker.setIcon(icon);
      } else {
        marker = L.marker([v.lat, v.lon], { icon, keyboard: true, zIndexOffset: 1000 })
          .bindPopup(() => this.vehiclePopup(key))
          .addTo(this.vehicleLayer);
        this.vehicleMarkers.set(key, marker);
      }
      marker.options.title = this.vehicleTitle(v);
      this.fadeVehicle(marker, v, h);
    }
    for (const [id, marker] of this.vehicleMarkers) {
      if (!seen.has(id)) {
        marker.remove();
        this.vehicleMarkers.delete(id);
      }
    }
  }

  private focusVehicle(m: L.Map | null, list: Vehicle[] | undefined, id: string | undefined): void {
    if (!m || !list || !id || this.focusedVehicle === id) return;
    const v = list.find((x) => vehicleKey(x) === id);
    const marker = this.vehicleMarkers.get(id);
    if (!v || !marker) return;
    this.focusedVehicle = id;
    this.fitted = true;
    m.setView([v.lat, v.lon], Math.max(m.getZoom(), 13));
    marker.openPopup();
  }

  private vehicleIcon(v: Vehicle): L.DivIcon {
    const bg = safeColor(v.route?.color, '#888888');
    const fg = safeColor(v.route?.text_color, '#000000');
    const number = v.short_name && v.short_name !== v.trip_id ? v.short_name : '';
    const label = escapeHtml((number || v.route?.short_name || '').slice(0, 4));
    const arrow =
      v.bearing == null || !Number.isFinite(v.bearing)
        ? ''
        : `<div class="veh-arrow" style="transform:rotate(${Math.round(v.bearing)}deg)"></div>`;
    return L.divIcon({
      className: 'veh-icon',
      html: `<div class="veh${v.source === 'estimated' ? ' estimated' : ''}" style="--c:${bg};--t:${fg}">${arrow}<div class="veh-disc">${label}</div></div>`,
      iconSize: [34, 34],
      iconAnchor: [17, 17],
      popupAnchor: [0, -16],
    });
  }

  /** Built at open time, so it reflects the latest poll. */
  private vehiclePopup(id: string): HTMLElement {
    const v = this.vehicles.data()?.find((x) => vehicleKey(x) === id);
    if (!v) return this.popup('Vehicle', 'No longer reporting', '', '');
    const title = this.vehicleTitle(v);
    const status = v.status ? VEHICLE_STATUS[v.status] ?? '' : '';
    const when = v.source === 'estimated' ? 'Estimated from predictions' : formatAge(v.timestamp, this.clock.now());
    const sub = [v.route?.short_name, status, when].filter(Boolean).join(' · ');
    return this.popup(title, sub, 'Trip details →', `/trips/${encodeURIComponent(v.trip_id)}`);
  }

  private vehicleTitle(v: Vehicle): string {
    const what = `${v.route ? `${this.op.agencyName(v.route.agency)} ` : ''}${tripLabel({ trip_id: v.trip_id, short_name: v.short_name ?? '', route: v.route })}`;
    return `${what}${v.headsign ? ` to ${stationName(v.headsign)}` : ''}`;
  }

  /** Popup content as DOM (no HTML strings from the API), with an SPA link. */
  private popup(title: string, sub: string, linkText: string, url: string): HTMLElement {
    const root = document.createElement('div');
    const t = document.createElement('span');
    t.className = 'popup-title';
    t.textContent = title;
    root.append(t);
    if (sub) {
      const s = document.createElement('span');
      s.className = 'popup-sub';
      s.textContent = sub;
      root.append(s);
    }
    if (url) {
      const a = document.createElement('a');
      a.className = 'popup-link';
      a.href = url;
      a.textContent = linkText;
      a.addEventListener('click', (e) => {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
        e.preventDefault();
        void this.router.navigateByUrl(url);
      });
      root.append(a);
    }
    return root;
  }
}
