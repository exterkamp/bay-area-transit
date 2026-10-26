import { Component, computed, inject, input } from '@angular/core';
import type { AgencyId } from '../api/models';
import { OperatorService } from '../core/operator.service';
import { compareAgencies } from '../lib/agencies';

/** "Muni" "BART" pills for the agencies serving a place. */
@Component({
  selector: 'app-agency-chips',
  template: `@for (id of sorted(); track id) {<span class="chip">{{ op.agencyName(id) }}</span>}`,
  styles: `
    :host { display: inline-flex; flex-wrap: wrap; gap: 0.25rem; }
    .chip {
      padding: 0 0.4rem;
      border-radius: 999px;
      border: 1px solid var(--line);
      color: var(--fg-soft);
      font-size: 0.7rem;
      font-weight: 600;
      line-height: 1.5;
      white-space: nowrap;
    }
  `,
})
export class AgencyChips {
  protected readonly op = inject(OperatorService);
  readonly ids = input<readonly AgencyId[]>([]);
  protected readonly sorted = computed(() => [...this.ids()].sort(compareAgencies));
}
