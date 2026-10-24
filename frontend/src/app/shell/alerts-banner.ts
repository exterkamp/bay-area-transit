import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { AlertsService } from '../core/alerts.service';
import { humanizeEnum, safeHttpUrl } from '../lib/format';

@Component({
  selector: 'app-alerts-banner',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (alerts.visible().length) {
      <section class="alerts" aria-label="Service alerts">
        @for (a of alerts.visible(); track a.id) {
          <article class="alert">
            <span class="icon" aria-hidden="true">!</span>
            <div class="body">
              @if (a.description) {
                <details>
                  <summary>
                    <strong>{{ a.header || effect(a.effect) || 'Service alert' }}</strong>
                  </summary>
                  <p>{{ a.description }}</p>
                  @if (link(a.url); as href) {
                    <a [href]="href" target="_blank" rel="noopener noreferrer">More info</a>
                  }
                </details>
              } @else {
                <strong>{{ a.header || effect(a.effect) || 'Service alert' }}</strong>
                @if (link(a.url); as href) {
                  · <a [href]="href" target="_blank" rel="noopener noreferrer">More info</a>
                }
              }
            </div>
            <button type="button" class="dismiss" (click)="alerts.dismiss(a.id)" aria-label="Dismiss alert">
              ×
            </button>
          </article>
        }
      </section>
    }
  `,
  styles: `
    .alerts { display: grid; gap: 0.5rem; margin: 0.75rem 0 0; }
    .alert {
      display: grid;
      grid-template-columns: auto 1fr auto;
      gap: 0.6rem;
      align-items: start;
      padding: 0.65rem 0.75rem;
      border-radius: var(--radius);
      background: var(--warn-bg);
      border: 1px solid var(--warn-line);
      font-size: 0.9rem;
    }
    .icon {
      display: grid;
      place-items: center;
      width: 1.25rem;
      height: 1.25rem;
      border-radius: 50%;
      background: var(--warn);
      color: var(--bg);
      font-weight: 800;
      font-size: 0.8rem;
      margin-top: 0.05rem;
    }
    .body { min-width: 0; overflow-wrap: anywhere; }
    summary { cursor: pointer; list-style-position: outside; }
    details p { margin: 0.4rem 0; white-space: pre-line; color: var(--fg-soft); }
    .dismiss {
      border: 0;
      background: transparent;
      color: var(--muted);
      font-size: 1.3rem;
      line-height: 1;
      width: 2rem;
      height: 2rem;
      margin: -0.35rem -0.35rem 0 0;
      border-radius: 50%;
      cursor: pointer;
    }
    .dismiss:hover { background: var(--surface-2); color: var(--fg); }
  `,
})
export class AlertsBanner {
  protected readonly alerts = inject(AlertsService);
  protected readonly effect = humanizeEnum;
  protected readonly link = safeHttpUrl;
}
