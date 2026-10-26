import { Component, computed, inject, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import type { PlanResponse, PlanTrip } from '../../api/models';
import { ClockService } from '../../core/clock.service';
import { OperatorService } from '../../core/operator.service';
import { delayInfo } from '../../lib/delay';
import { tripLabel } from '../../lib/agencies';
import { stationName, stopsText } from '../../lib/format';
import { routeLabel } from '../../lib/plan-scope';
import { countdown, formatDuration } from '../../lib/time';
import { RouteBadge } from '../../shared/route-badge';
import { StateView } from '../../shared/state';
import { StationNamePipe } from '../../shared/station-name.pipe';
import { StopTimeView } from '../../shared/stop-time';
import { PlannerStore } from './planner.store';

/**
 * Trips planned on one agency at a time: pick it, then the stations it calls
 * at fill the dropdowns. Agencies too big for one list (Muni, SamTrans) ask
 * for a line first and list its stops.
 */
@Component({
  selector: 'app-planner-page',
  imports: [RouterLink, RouteBadge, StateView, StopTimeView, StationNamePipe],
  providers: [PlannerStore],
  templateUrl: './planner-page.html',
  styleUrl: './planner-page.scss',
})
export class PlannerPage {
  protected readonly op = inject(OperatorService);
  protected readonly store = inject(PlannerStore);
  private readonly clock = inject(ClockService);

  /** Optional ?from=&to= place ids (e.g. "Plan from here" on a board) override the remembered plan. */
  readonly from = input<string>();
  readonly to = input<string>();

  constructor() {
    this.store.restore(
      computed(() => {
        const code = this.store.readyCode();
        return code ? { code, from: this.from(), to: this.to() } : null;
      }),
    );
  }

  protected countdownFor(t: PlanTrip): string {
    if (t.status === 'canceled' || this.store.mode() !== 'now') return '';
    return countdown(delayInfo(t.depart).effective, this.clock.now());
  }

  protected noTripsTitle(p: PlanResponse): string {
    return p.served ? 'Nothing in the next day' : 'No direct trips';
  }

  /** Empty: either the trip runs on other days, or it needs a transfer the planner can't plan. */
  protected noDirectMessage(p: PlanResponse): string {
    const from = stationName(p.from.name);
    const to = stationName(p.to.name);
    if (p.served) {
      return `Trips from ${from} to ${to} run on other days. Pick "Depart at" and a later date to see them.`;
    }
    return (
      `No ${this.store.scopeName()} trip runs straight from ${from} to ${to}. ` +
      "It may need a transfer, and the planner doesn't plan those yet. The departure boards at each end show what leaves from where."
    );
  }

  protected readonly duration = formatDuration;
  protected readonly routeLabel = routeLabel;
  protected readonly tripLabel = tripLabel;
  protected readonly stopsText = stopsText;
}
