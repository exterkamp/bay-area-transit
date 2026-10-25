import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { ClockService } from './core/clock.service';
import { OperatorService } from './core/operator.service';
import { dateInRange, todayInZone } from './lib/time';
import { DayPipe } from './shared/time.pipe';
import { AlertsBanner } from './shell/alerts-banner';
import { RealtimeIndicator } from './shell/realtime-indicator';

@Component({
  selector: 'app-root',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterOutlet, RouterLink, RouterLinkActive, AlertsBanner, RealtimeIndicator, DayPipe],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  protected readonly op = inject(OperatorService);
  private readonly clock = inject(ClockService);

  /** The feed's validity window doesn't cover today. */
  protected readonly feedOutOfRange = computed(() => {
    const f = this.op.feed();
    if (!f) return false;
    this.clock.now();
    return !dateInRange(todayInZone(this.op.timeZone()), f.start_date, f.end_date);
  });
}
