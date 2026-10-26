import { Component, computed, inject } from '@angular/core';
import { ClockService } from '../core/clock.service';
import { OperatorService } from '../core/operator.service';
import { dateInRange, todayInZone } from '../lib/time';
import { DayPipe } from '../shared/time.pipe';

/** The timetable's dates, a warning when they don't cover today, and credits. */
@Component({
  selector: 'app-feed-note',
  imports: [DayPipe],
  template: `
    @if (op.feed(); as f) {
      <p>
        @if (firstToEnd(); as first) {
          Timetables valid through {{ f.end_date | day }}
          <span class="sep">·</span> {{ first }}'s runs out first
        } @else {
          Timetable valid {{ f.start_date | day }} – {{ f.end_date | day }}
          @if (f.version) {
            <span class="sep">·</span> feed {{ f.version }}
          }
        }
      </p>
      @if (feedOutOfRange()) {
        <p class="warn">
          @if (firstToEnd(); as first) {
            {{ first }}'s timetable has run out — its times may be wrong.
          } @else {
            Today is outside this timetable's dates — times may be wrong.
          }
        </p>
      }
    } @else if (op.noFeed()) {
      <p>No timetable has been imported yet.</p>
    } @else if (op.operators.error(); as e) {
      <p>{{ e.title }}</p>
    }
    <p class="credits">Map data © OpenStreetMap contributors. Transit data from 511.org. Not affiliated with {{ op.multiAgency() ? 'the transit agencies' : op.name() }}.</p>
  `,
  styles: `
    :host { display: block; }
    p { margin: 0.2rem 0; }
    .warn { color: var(--warn); font-weight: 600; }
    .credits { opacity: 0.8; }
    .sep { margin-inline: 0.25rem; }
  `,
})
export class FeedNote {
  protected readonly op = inject(OperatorService);
  private readonly clock = inject(ClockService);

  /** In a merged feed, the agency whose timetable runs out first: its end is the feed's. */
  protected readonly firstToEnd = computed(() => {
    if (!this.op.multiAgency()) return null;
    const dated = (this.op.agencies.data() ?? []).filter((a) => a.feed);
    dated.sort((a, b) => a.feed!.end_date.localeCompare(b.feed!.end_date));
    return dated[0] ? this.op.agencyName(dated[0].id) : null;
  });

  /** The feed's validity window doesn't cover today. */
  protected readonly feedOutOfRange = computed(() => {
    const f = this.op.feed();
    if (!f) return false;
    this.clock.now();
    return !dateInRange(todayInZone(this.op.timeZone()), f.start_date, f.end_date);
  });
}
