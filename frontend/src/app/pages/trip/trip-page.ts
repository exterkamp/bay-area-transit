import { ChangeDetectionStrategy, Component, computed, effect, inject, input } from '@angular/core';
import { Title } from '@angular/platform-browser';
import { RouterLink } from '@angular/router';
import type { StopTime, TripDetail, TripStop, VehicleStatus } from '../../api/models';
import { apiUrls } from '../../api/urls';
import { ClockService } from '../../core/clock.service';
import { OperatorService } from '../../core/operator.service';
import { polled } from '../../core/polled';
import { tripLabel, vehicleKey, vehicleNoun } from '../../lib/agencies';
import { delayInfo } from '../../lib/delay';
import { stationName } from '../../lib/format';
import { formatAge, formatInstant } from '../../lib/time';
import { RouteBadge } from '../../shared/route-badge';
import { StateView } from '../../shared/state';
import { StopTimeView } from '../../shared/stop-time';
import { StationNamePipe } from '../../shared/station-name.pipe';
import { ServiceDayPipe } from '../../shared/time.pipe';

interface StopRow {
  stop: TripStop;
  /** Departure everywhere but the last stop, where it's the arrival. */
  time: StopTime;
  passed: boolean;
  /** This is the stop the live vehicle is at / heading to. */
  vehicleHere: VehicleStatus | undefined;
}

const VEHICLE_TEXT: Record<Exclude<VehicleStatus, null>, string> = {
  incoming_at: 'Arriving at',
  stopped_at: 'Stopped at',
  in_transit_to: 'On the way to',
};

@Component({
  selector: 'app-trip-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, RouteBadge, StateView, StopTimeView, ServiceDayPipe, StationNamePipe],
  templateUrl: './trip-page.html',
  styleUrl: './trip-page.scss',
})
export class TripPage {
  protected readonly op = inject(OperatorService);
  private readonly clock = inject(ClockService);
  private readonly title = inject(Title);

  /** Route param :tripId. */
  readonly tripId = input.required<string>();
  /** ?date=YYYY-MM-DD, the service date. Omitted means today (the API's default). */
  readonly date = input<string>();

  protected readonly trip = polled<TripDetail>(
    () => (this.op.noFeed() ? undefined : apiUrls.trip(this.op.code(), this.tripId(), this.date())),
    { intervalMs: 30_000, what: 'that trip' },
  );

  protected readonly noun = computed(() => vehicleNoun(this.trip.data()?.route));
  protected readonly tripLabel = tripLabel;
  protected readonly vehicleKey = vehicleKey;

  protected readonly rows = computed<StopRow[]>(() => {
    const t = this.trip.data();
    if (!t) return [];
    const now = this.clock.now();
    const last = t.stops.length - 1;
    const v = t.vehicle;
    return t.stops.map((stop, i) => {
      const time = i === last ? stop.arrival : stop.departure;
      const effective = Date.parse(delayInfo(time).effective);
      return {
        stop,
        time,
        passed: effective < now - 30_000,
        vehicleHere: v && v.stop_id === stop.stop_id ? v.status : undefined,
      };
    });
  });

  protected readonly vehicleLine = computed(() => {
    const t = this.trip.data();
    const v = t?.vehicle;
    if (!t || !v) return '';
    const stop = t.stops.find((s) => s.stop_id === v.stop_id);
    // The Caltrain feed sends no stop_id/status, so this is often all we can say.
    if (!stop || !v.status) return v.source === 'estimated' ? 'Estimated position' : 'Live position';
    const line = `${VEHICLE_TEXT[v.status]} ${stationName(stop.name)}`;
    return v.source === 'estimated' ? `${line} (estimated)` : line;
  });

  protected readonly vehicleAge = computed(() => {
    const v = this.trip.data()?.vehicle;
    // An estimate is computed per request, so its age says nothing.
    return v && v.source === 'gps' ? formatAge(v.timestamp, this.clock.now()) : '';
  });

  protected readonly updated = computed(() => {
    const t = this.trip.updatedAt();
    return t ? formatInstant(t, this.op.timeZone()) : '';
  });

  constructor() {
    effect(() => {
      const t = this.trip.data();
      if (t) this.title.setTitle(`${tripLabel(t)} to ${stationName(t.headsign)} · Bay Area Transit`);
    });
  }
}
