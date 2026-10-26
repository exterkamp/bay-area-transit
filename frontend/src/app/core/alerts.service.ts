import { Service, computed, inject, signal } from '@angular/core';
import type { Alert } from '../api/models';
import { apiUrls } from '../api/urls';
import { pruneDismissed, visibleAlerts } from '../lib/format';
import { STORAGE_KEYS, readJson, writeJson } from '../lib/storage';
import { OperatorService } from './operator.service';
import { polled } from './polled';

@Service()
export class AlertsService {
  private readonly op = inject(OperatorService);

  readonly alerts = polled<Alert[]>(
    () => (this.op.noFeed() || this.op.unknownOperator() ? undefined : apiUrls.alerts(this.op.code())),
    { intervalMs: 60_000 },
  );

  private readonly dismissed = signal<string[]>(readJson<string[]>(STORAGE_KEYS.dismissedAlerts, []));

  readonly visible = computed(() => visibleAlerts(this.alerts.data() ?? [], new Set(this.dismissed())));

  /** With several alerts the banner is one bar until opened; this session only. */
  readonly expanded = signal(false);

  dismissAll(): void {
    this.setDismissed([...new Set([...this.dismissed(), ...this.visible().map((a) => a.id)])]);
    this.expanded.set(false);
  }

  dismiss(id: string): void {
    if (!this.dismissed().includes(id)) this.setDismissed([...this.dismissed(), id]);
  }

  /** Dismissals of alerts that have since ended are forgotten on the next write. */
  private setDismissed(ids: string[]): void {
    ids = pruneDismissed(ids, this.alerts.data() ?? []);
    this.dismissed.set(ids);
    writeJson(STORAGE_KEYS.dismissedAlerts, ids);
  }
}
