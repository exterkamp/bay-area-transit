import { Component, computed, inject } from '@angular/core';
import { ClockService } from '../core/clock.service';
import { OperatorService } from '../core/operator.service';
import { realtimeLabel } from '../lib/staleness';
import { formatAge, formatTime } from '../lib/time';

@Component({
  selector: 'app-realtime-indicator',
  template: `
    @if (op.operator()) {
      <span class="pill" [attr.data-status]="rt().status" [attr.title]="tooltip()">
        <span class="dot" aria-hidden="true"></span>
        {{ label() }}
      </span>
    }
  `,
  styles: `
    .pill {
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      font-size: 0.75rem;
      font-weight: 600;
      padding: 0.2rem 0.55rem;
      border-radius: 999px;
      background: var(--surface-2);
      color: var(--muted);
      white-space: nowrap;
    }
    .dot { width: 0.5rem; height: 0.5rem; border-radius: 50%; background: currentColor; }
    [data-status='fresh'] { color: var(--ok); }
    [data-status='fresh'] .dot { animation: pulse 2.4s ease-in-out infinite; }
    [data-status='stale'] { color: var(--warn); background: var(--warn-bg); }
    @keyframes pulse { 50% { opacity: 0.35; } }
    @media (prefers-reduced-motion: reduce) { [data-status='fresh'] .dot { animation: none; } }
  `,
})
export class RealtimeIndicator {
  protected readonly op = inject(OperatorService);
  private readonly clock = inject(ClockService);
  protected readonly rt = this.op.realtime;

  protected readonly label = computed(() => realtimeLabel(this.rt(), formatTime));

  protected readonly tooltip = computed(() => {
    const r = this.rt();
    if (r.status === 'unavailable') return 'Realtime is unavailable; times shown are from the timetable.';
    const when = r.latest ? ` Last fetched ${formatAge(r.latest, this.clock.now())}.` : '';
    if (r.status === 'stale') return `Realtime updates have stopped arriving; times may not reflect delays.${when}`;
    return `Realtime predictions are current.${when}`;
  });
}
