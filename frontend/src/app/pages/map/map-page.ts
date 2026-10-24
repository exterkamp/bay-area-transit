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
  signal,
  viewChild,
} from '@angular/core';
import { Router } from '@angular/router';
import * as L from 'leaflet';
import type { Route, ShapeCollection, Station, Vehicle } from '../../api/models';
import { apiUrls } from '../../api/urls';
import { ClockService } from '../../core/clock.service';
import { OperatorService } from '../../core/operator.service';
import { polled } from '../../core/polled';
import { escapeHtml, safeColor, stationName } from '../../lib/format';
import { formatAge, formatInstant } from '../../lib/time';
import { StateView } from '../../shared/state';

/** Roughly the Caltrain corridor, for before anything has loaded. */
const DEFAULT_CENTER: L.LatLngExpression = [37.55, -122.25];
const DEFAULT_ZOOM = 9;

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

  /** ?vehicle=<vehicle_id> centers on that train once it shows up. */
  readonly vehicle = input<string>();

  private readonly mapEl = viewChild.required<ElementRef<HTMLDivElement>>('map');
  private readonly map = signal<L.Map | null>(null);

  private readonly code = computed(() => (this.op.noFeed() ? undefined : this.op.code()));

  protected readonly shapes = polled<ShapeCollection>(() => {
    const c = this.code();
    return c && apiUrls.shapes(c);
  });
  protected readonly routes = polled<Route[]>(() => {
    const c = this.code();
    return c && apiUrls.routes(c);
  });
  protected readonly vehicles = polled<Vehicle[]>(
    () => {
      const c = this.code();
      return c && apiUrls.vehicles(c);
    },
    { intervalMs: 30_000 },
  );
  protected readonly stations = this.op.stations;

  /** Legend: routes that actually have a shape drawn. */
  protected readonly legend = computed(() => {
    const drawn = new Set((this.shapes.data()?.features ?? []).map((f) => f.properties.route_id));
    return (this.routes.data() ?? []).filter((r) => drawn.has(r.id));
  });

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

  protected readonly vehiclesUpdated = computed(() => {
    const t = this.vehicles.updatedAt();
    return t ? formatInstant(t, this.op.timeZone()) : '';
  });

  private shapeLayer: L.LayerGroup | null = null;
  private stationLayer: L.FeatureGroup | null = null;
  private readonly vehicleLayer = L.layerGroup();
  private readonly vehicleMarkers = new Map<string, L.Marker>();
  private fitted = false;
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
      this.map.set(m);
      // The container may have been sized after Leaflet measured it.
      setTimeout(() => m.invalidateSize(), 0);
    });

    inject(DestroyRef).onDestroy(() => this.map()?.remove());

    effect(() => this.drawShapes(this.map(), this.shapes.data()));
    effect(() => this.drawStations(this.map(), this.stations.data()));
    effect(() => this.drawVehicles(this.map(), this.vehicles.data()));
    effect(() => this.focusVehicle(this.map(), this.vehicles.data(), this.vehicle()));
  }

  private drawShapes(m: L.Map | null, fc: ShapeCollection | undefined): void {
    if (!m || !fc) return;
    this.shapeLayer?.remove();
    // A dark casing under each line keeps pale route colors visible on the basemap.
    const casing = L.geoJSON(fc as GeoJSON.FeatureCollection, {
      style: () => ({ color: '#1b1d1f', weight: 7, opacity: 0.55, lineCap: 'round', lineJoin: 'round' }),
      interactive: false,
    });
    const lines = L.geoJSON(fc as GeoJSON.FeatureCollection, {
      style: (f) => ({
        color: safeColor((f?.properties as { color?: string } | undefined)?.color),
        weight: 4,
        opacity: 0.95,
        lineCap: 'round',
        lineJoin: 'round',
      }),
      interactive: false,
    });
    this.shapeLayer = L.layerGroup([casing, lines]).addTo(m);
    const b = lines.getBounds();
    if (!this.fitted && b.isValid() && !this.vehicle()) {
      m.fitBounds(b, { padding: [24, 24] });
      this.fitted = true;
    }
  }

  private drawStations(m: L.Map | null, list: Station[] | undefined): void {
    if (!m || !list) return;
    this.stationLayer?.remove();
    const markers = list.map((s) =>
      L.circleMarker([s.lat, s.lon], {
        radius: 6,
        color: '#1b1d1f',
        weight: 2,
        fillColor: '#ffffff',
        fillOpacity: 1,
        pane: 'stations',
      })
        .bindTooltip(stationName(s.name), { direction: 'top', offset: [0, -6] })
        .bindPopup(() => this.popup(stationName(s.name), '', 'Departures →', `/stations/${encodeURIComponent(s.id)}`)),
    );
    this.stationLayer = L.featureGroup(markers).addTo(m);
    const b = this.stationLayer.getBounds();
    if (!this.fitted && b.isValid() && !this.shapes.data() && !this.vehicle()) {
      m.fitBounds(b, { padding: [24, 24] });
      this.fitted = true;
    }
  }

  private drawVehicles(m: L.Map | null, list: Vehicle[] | undefined): void {
    if (!m || !list) return;
    const seen = new Set<string>();
    for (const v of list) {
      seen.add(v.vehicle_id);
      const icon = this.vehicleIcon(v);
      let marker = this.vehicleMarkers.get(v.vehicle_id);
      if (marker) {
        marker.setLatLng([v.lat, v.lon]);
        marker.setIcon(icon);
      } else {
        marker = L.marker([v.lat, v.lon], { icon, keyboard: true, zIndexOffset: 1000 })
          .bindPopup(() => this.vehiclePopup(v.vehicle_id))
          .addTo(this.vehicleLayer);
        this.vehicleMarkers.set(v.vehicle_id, marker);
      }
      marker.options.title = `Train ${v.short_name ?? v.trip_id}`;
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
    const v = list.find((x) => x.vehicle_id === id);
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
    const label = escapeHtml((v.short_name ?? v.trip_id ?? '').slice(0, 4));
    const arrow =
      v.bearing == null || !Number.isFinite(v.bearing)
        ? ''
        : `<div class="veh-arrow" style="transform:rotate(${Math.round(v.bearing)}deg)"></div>`;
    return L.divIcon({
      className: 'veh-icon',
      html: `<div class="veh" style="--c:${bg};--t:${fg}">${arrow}<div class="veh-disc">${label}</div></div>`,
      iconSize: [34, 34],
      iconAnchor: [17, 17],
      popupAnchor: [0, -16],
    });
  }

  /** Built at open time, so it reflects the latest poll. */
  private vehiclePopup(id: string): HTMLElement {
    const v = this.vehicles.data()?.find((x) => x.vehicle_id === id);
    if (!v) return this.popup('Train', 'No longer reporting', '', '');
    const title = `Train ${v.short_name ?? v.trip_id}${v.headsign ? ` to ${v.headsign}` : ''}`;
    const status = v.status ? VEHICLE_STATUS[v.status] ?? '' : '';
    const sub = [v.route?.short_name, status, formatAge(v.timestamp, this.clock.now())].filter(Boolean).join(' · ');
    return this.popup(title, sub, 'Trip details →', `/trips/${encodeURIComponent(v.trip_id)}`);
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
