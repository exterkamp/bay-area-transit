import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import type { StopTime } from '../api/models';
import { delayInfo, delaySeverity } from '../lib/delay';
import { formatTime } from '../lib/time';

/**
 * One time, with its realtime story: the schedule alone; the schedule struck
 * out beside the estimate and "+3 min"; or "On time" when live and on time.
 */
@Component({
  selector: 'app-stop-time',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { '[class.canceled]': 'canceled()' },
  template: `
    @let i = info();
    @if (i.changed && !canceled()) {
      <s class="sched" aria-label="Scheduled {{ scheduled() }}">{{ scheduled() }}</s>
      <time class="est" [attr.datetime]="i.effective">{{ effective() }}</time>
      @if (showDelay()) {
        <span class="delay" [attr.data-sev]="sev()">{{ i.text }}</span>
      }
    } @else {
      <time [attr.datetime]="time().scheduled">{{ scheduled() }}</time>
      @if (i.hasEstimate && showDelay() && !canceled()) {
        <span class="delay" data-sev="ontime">On time</span>
      }
    }
  `,
  styles: `
    :host { display: inline-flex; align-items: baseline; gap: 0.35rem; flex-wrap: wrap; font-variant-numeric: tabular-nums; }
    :host(.canceled) time { text-decoration: line-through; text-decoration-thickness: 1.5px; color: var(--muted); }
    .sched { color: var(--muted); font-size: 0.85em; text-decoration-thickness: 1.5px; }
    .est { font-weight: 650; }
    .delay { font-size: 0.75rem; font-weight: 600; white-space: nowrap; }
    .delay[data-sev='ontime'] { color: var(--ok); }
    .delay[data-sev='early'] { color: var(--ok); }
    .delay[data-sev='minor'] { color: var(--warn); }
    .delay[data-sev='major'] { color: var(--bad); }
  `,
})
export class StopTimeView {
  readonly time = input.required<StopTime>();
  readonly canceled = input(false);
  readonly showDelay = input(true);

  protected readonly info = computed(() => delayInfo(this.time()));
  protected readonly scheduled = computed(() => formatTime(this.time().scheduled));
  protected readonly effective = computed(() => formatTime(this.info().effective));
  protected readonly sev = computed(() => delaySeverity(this.info().minutes));
}
