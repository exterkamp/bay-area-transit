import { Component, computed, input } from '@angular/core';
import type { RouteRef } from '../api/models';
import { safeColor } from '../lib/format';

@Component({
  selector: 'app-route-badge',
  template: `<span class="route-badge" [style.background]="bg()" [style.color]="fg()">{{ label() }}</span>`,
  styles: `
    :host { display: inline-flex; }
    .route-badge {
      display: inline-block;
      padding: 0.1rem 0.45rem;
      border-radius: 999px;
      font-size: 0.72rem;
      font-weight: 650;
      letter-spacing: 0.01em;
      line-height: 1.35;
      white-space: nowrap;
      box-shadow: inset 0 0 0 1px rgb(0 0 0 / 0.12);
    }
  `,
})
export class RouteBadge {
  readonly route = input<RouteRef | null>(null);
  protected readonly bg = computed(() => safeColor(this.route()?.color, '#888888'));
  protected readonly fg = computed(() => safeColor(this.route()?.text_color, '#000000'));
  protected readonly label = computed(() => this.route()?.short_name || this.route()?.id || 'Train');
}
