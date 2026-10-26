import { Component, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute, NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter, map } from 'rxjs';
import { OperatorService } from './core/operator.service';
import { AlertsBanner } from './shell/alerts-banner';
import { FeedNote } from './shell/feed-note';
import { RealtimeIndicator } from './shell/realtime-indicator';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, AlertsBanner, RealtimeIndicator, FeedNote],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  protected readonly op = inject(OperatorService);
  private readonly route = inject(ActivatedRoute);

  /** The page asks for the whole window on large screens (the map). */
  protected readonly fullBleed = toSignal(
    inject(Router).events.pipe(
      filter((e) => e instanceof NavigationEnd),
      map(() => {
        let r = this.route.snapshot;
        while (r.firstChild) r = r.firstChild;
        return !!r.data['fullBleed'];
      }),
    ),
    { initialValue: false },
  );
}
