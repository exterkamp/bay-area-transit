import { Injectable, computed, effect, inject, signal } from '@angular/core';
import type { Alert } from '../api/models';
import { apiUrls } from '../api/urls';
import { pruneDismissed, visibleAlerts } from '../lib/format';
import { STORAGE_KEYS, readJson, writeJson } from '../lib/storage';
import { OperatorService } from './operator.service';
import { polled } from './polled';

@Injectable({ providedIn: 'root' })
export class AlertsService {
  private readonly op = inject(OperatorService);

  readonly alerts = polled<Alert[]>(
    () => (this.op.noFeed() || this.op.unknownOperator() ? undefined : apiUrls.alerts(this.op.code())),
    { intervalMs: 60_000 },
  );

  private readonly dismissed = signal<string[]>(readJson<string[]>(STORAGE_KEYS.dismissedAlerts, []));

  readonly visible = computed(() => visibleAlerts(this.alerts.data() ?? [], new Set(this.dismissed())));

  constructor() {
    // Forget dismissals for alerts that have ended.
    effect(() => {
      const list = this.alerts.data();
      if (!list) return;
      const pruned = pruneDismissed(this.dismissed(), list);
      if (pruned.length !== this.dismissed().length) this.setDismissed(pruned);
    });
  }

  dismiss(id: string): void {
    if (!this.dismissed().includes(id)) this.setDismissed([...this.dismissed(), id]);
  }

  private setDismissed(ids: string[]): void {
    this.dismissed.set(ids);
    writeJson(STORAGE_KEYS.dismissedAlerts, ids);
  }
}
