import { ChangeDetectionStrategy, Component, computed, effect, inject, input } from '@angular/core';
import { Title } from '@angular/platform-browser';
import { RouterLink } from '@angular/router';
import type { Departure, DeparturesResponse } from '../../api/models';
import { apiUrls } from '../../api/urls';
import { ClockService } from '../../core/clock.service';
import { OperatorService } from '../../core/operator.service';
import { polled } from '../../core/polled';
import { delayInfo } from '../../lib/delay';
import { stationName } from '../../lib/format';
import { findStation, groupByDirection } from '../../lib/stations';
import { countdown, formatInstant } from '../../lib/time';
import { RouteBadge } from '../../shared/route-badge';
import { StateView } from '../../shared/state';
import { StationNamePipe } from '../../shared/station-name.pipe';
import { StopTimeView } from '../../shared/stop-time';

@Component({
  selector: 'app-station-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, RouteBadge, StateView, StopTimeView, StationNamePipe],
  templateUrl: './station-page.html',
  styleUrl: './station-page.scss',
})
export class StationPage {
  protected readonly op = inject(OperatorService);
  private readonly clock = inject(ClockService);
  private readonly title = inject(Title);

  /** Route param :id. */
  readonly id = input.required<string>();

  protected readonly board = polled<DeparturesResponse>(
    () => (this.op.noFeed() ? undefined : apiUrls.departures(this.op.code(), this.id(), { limit: 30 })),
    { intervalMs: 60_000, what: 'that station' },
  );

  protected readonly station = computed(() => findStation(this.op.stations.data() ?? [], this.id()));
  protected readonly name = computed(() =>
    stationName(this.board.data()?.station.name ?? this.station()?.name ?? ''),
  );

  protected readonly groups = computed(() =>
    groupByDirection(this.op.stations.data() ?? [], this.id(), this.board.data()?.departures ?? []),
  );

  protected readonly updated = computed(() => {
    const t = this.board.updatedAt();
    return t ? formatInstant(t, this.op.timeZone()) : '';
  });

  constructor() {
    effect(() => {
      const n = this.name();
      if (n) this.title.setTitle(`${n} departures · Bay Area Transit`);
    });
  }

  protected countdownFor(d: Departure): string {
    if (d.status === 'canceled') return '';
    return countdown(delayInfo(d.depart).effective, this.clock.now());
  }
}
