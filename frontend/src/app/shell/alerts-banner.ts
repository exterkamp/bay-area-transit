import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import type { Alert } from '../api/models';
import { AlertsService } from '../core/alerts.service';
import { OperatorService } from '../core/operator.service';
import { alertAgencies, humanizeEnum, safeHttpUrl } from '../lib/format';

@Component({
  selector: 'app-alerts-banner',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (collapsed()) {
      <section class="alerts" aria-label="Service alerts">
        <button type="button" class="alert summary" aria-expanded="false" (click)="alerts.expanded.set(true)">
          <span class="icon" aria-hidden="true">!</span>
          <span class="body">
            <strong>{{ alerts.visible().length }} service alerts</strong>
            @if (agencies()) {
              <span class="who"> · {{ agencies() }}</span>
            }
            <span class="first">{{ title(alerts.visible()[0]!) }}</span>
          </span>
          <span class="chevron" aria-hidden="true">▾</span>
        </button>
      </section>
    } @else if (alerts.visible().length) {
      <section class="alerts" aria-label="Service alerts">
        @if (alerts.visible().length > 1) {
          <div class="bar">
            <button type="button" class="link" aria-expanded="true" (click)="alerts.expanded.set(false)">
              Hide {{ alerts.visible().length }} alerts ▴
            </button>
            <button type="button" class="link" (click)="alerts.dismissAll()">Dismiss all</button>
          </div>
        }
        @for (a of alerts.visible(); track a.id) {
          <article class="alert">
            <span class="icon" aria-hidden="true">!</span>
            <div class="body">
              @if (a.description) {
                <details>
                  <summary>
                    <strong>{{ title(a) }}</strong>
                  </summary>
                  <p>{{ a.description }}</p>
                  @if (link(a.url); as href) {
                    <a [href]="href" target="_blank" rel="noopener noreferrer">More info</a>
                  }
                </details>
              } @else {
                <strong>{{ title(a) }}</strong>
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
    .summary {
      width: 100%;
      text-align: left;
      font: inherit;
      font-size: 0.9rem;
      color: var(--fg);
      cursor: pointer;
      align-items: center;
    }
    .summary .who { color: var(--fg-soft); }
    .summary .first {
      display: block;
      color: var(--muted);
      font-size: 0.82rem;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .chevron { color: var(--muted); padding: 0 0.25rem; }
    .bar { display: flex; justify-content: space-between; gap: 1rem; }
    .link {
      border: 0;
      padding: 0.15rem 0;
      background: none;
      color: var(--accent);
      font: inherit;
      font-size: 0.85rem;
      font-weight: 600;
      cursor: pointer;
    }
  `,
})
export class AlertsBanner {
  protected readonly alerts = inject(AlertsService);
  private readonly op = inject(OperatorService);

  /** Several alerts start as one bar, so they don't push the page off screen. */
  protected readonly collapsed = computed(() => this.alerts.visible().length > 1 && !this.alerts.expanded());
  protected readonly agencies = computed(() =>
    this.op.multiAgency() ? alertAgencies(this.alerts.visible(), (id) => this.op.agencyName(id)) : '',
  );

  protected title(a: Alert): string {
    return a.header || humanizeEnum(a.effect) || 'Service alert';
  }
  protected readonly effect = humanizeEnum;
  protected readonly link = safeHttpUrl;
}
