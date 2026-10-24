import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  ElementRef,
  afterNextRender,
  computed,
  effect,
  inject,
  input,
  WritableSignal,
  signal,
  untracked,
  viewChild,
} from '@angular/core';
import { Router } from '@angular/router';
import * as L from 'leaflet';
import { firstValueFrom } from 'rxjs';
import type { AgencyId, Place, Route, ShapeCollection, Vehicle } from '../../api/models';
import { apiUrls } from '../../api/urls';
import { ClockService } from '../../core/clock.service';
import { OperatorService } from '../../core/operator.service';
import { polled } from '../../core/polled';
import { tripLabel, vehicleKey } from '../../lib/agencies';
import { escapeHtml, safeColor, stationName } from '../../lib/format';
import { legendEntries } from '../../lib/legend';
import { STORAGE_KEYS, readJson, writeJson } from '../../lib/storage';
import { formatAge, formatInstant } from '../../lib/time';
import { StateView } from '../../shared/state';

/** San Francisco and the Peninsula, for before anything has loaded. */
const DEFAULT_CENTER: L.LatLngExpression = [37.6, -122.35];
const DEFAULT_ZOOM = 10;
/** Street stops (as opposed to stations) only show from this zoom in. */
const STOPS_ZOOM = 14;
const RAIL_TYPES = new Set([0, 1, 2, 5, 12]);

/** One agency's lines and places, fetched once per visit and kept. */
interface AgencyLayers {
  shapes: L.LayerGroup;
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
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [StateView],
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

  /** Agencies drawn on the map; null until the agency list is known. */
  protected readonly selected = signal<ReadonlySet<AgencyId> | null>(null);
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
  private readonly renderer = L.canvas({ padding: 0.5 });
  private readonly vehicleLayer = L.layerGroup();
  private readonly vehicleMarkers = new Map<string, L.Marker>();
  protected fitted = false;
  private focusedVehicle = '';

  protected readonly safeColor = safeColor;

  constructor() {
    afterNextRender(() => {
      const m = L.map(this.mapEl().nativeElement, {
        center: DEFAULT_CENTER,
        zoom: DEFAULT_ZOOM,
        zoomControl: true,
        attributionControl: false,
      });
      L.control.attribution({ prefix: false }).addTo(m);
      L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      }).addTo(m);
      // Stations sit above the route lines (overlayPane, 400) and below trains (markerPane, 600).
      m.createPane('stations').style.zIndex = '450';
      this.vehicleLayer.addTo(m);
      m.on('zoomend', () => {
        for (const layers of this.layers.values()) this.updateStops(m, layers);
      });
      this.map.set(m);
      // The container may have been sized after Leaflet measured it.
      setTimeout(() => m.invalidateSize(), 0);
    });

    inject(DestroyRef).onDestroy(() => this.map()?.remove());

    // Start with the rail agencies, or whatever was shown last time.
    effect(() => {
      const agencies = this.op.agencies.data();
      if (!agencies || this.selected()) return;
      const ids = new Set(agencies.map((a) => a.id));
      const stored = readJson<unknown>(STORAGE_KEYS.mapAgencies(this.op.code()), null);
      const remembered = Array.isArray(stored) ? stored.filter((id): id is string => ids.has(id)) : [];
      const rail = agencies.filter((a) => a.route_types.some((t) => RAIL_TYPES.has(t))).map((a) => a.id);
      this.selected.set(new Set(remembered.length ? remembered : rail.length ? rail : [...ids]));
    });
    effect(() => this.syncLayers(this.map(), this.selected()));
    effect(() => this.drawVehicles(this.map(), this.vehicles.data()));
    effect(() => this.focusVehicle(this.map(), this.vehicles.data(), this.vehicle()));
  }

  protected readonly failedNames = computed(() =>
    [...this.failedAgencies()].map((id) => this.op.agencyName(id)).join(' and '),
  );

  protected retry(): void {
    this.failedAgencies.set(new Set());
    this.syncLayers(this.map(), this.selected());
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
      const layers = { shapes: this.shapeLayer(shapes), ...this.placeLayers(places) };
      this.layers.set(id, layers);
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
    if (m.getZoom() >= STOPS_ZOOM && m.hasLayer(layers.stations)) layers.stops.addTo(m);
    else layers.stops.remove();
  }

  private shapeLayer(fc: ShapeCollection): L.LayerGroup {
    // A dark casing under each line keeps pale route colors visible on the basemap.
    const casing = L.geoJSON(fc as GeoJSON.FeatureCollection, {
      style: () => ({ color: '#1b1d1f', weight: 6, opacity: 0.5, lineCap: 'round', lineJoin: 'round' }),
      interactive: false,
    });
    const lines = L.geoJSON(fc as GeoJSON.FeatureCollection, {
      style: (f) => ({
        color: safeColor((f?.properties as { color?: string } | undefined)?.color),
        weight: 3.5,
        opacity: 0.95,
        lineCap: 'round',
        lineJoin: 'round',
      }),
      interactive: false,
    });
    return L.layerGroup([casing, lines]);
  }

  private placeLayers(places: Place[]): Pick<AgencyLayers, 'stations' | 'stops'> {
    const marker = (p: Place, radius: number) =>
      L.circleMarker([p.lat, p.lon], {
        radius,
        color: '#1b1d1f',
        weight: radius > 4 ? 2 : 1.5,
        fillColor: '#ffffff',
        fillOpacity: 1,
        pane: 'stations',
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
      stations: L.featureGroup(places.filter((p) => p.kind === 'station').map((p) => marker(p, 6))),
      stops: L.layerGroup(places.filter((p) => p.kind === 'stop').map((p) => marker(p, 3.5))),
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
      m.fitBounds(bounds, { padding: [24, 24] });
      this.fitted = true;
    }
  }

  private drawVehicles(m: L.Map | null, list: Vehicle[] | undefined): void {
    if (!m || !list) return;
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
