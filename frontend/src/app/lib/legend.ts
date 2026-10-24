// Map legend entries. Framework-free.

import type { AgencyId, Route } from '../api/models';
import { agencyName, compareAgencies } from './agencies';

export interface LegendEntry {
  label: string;
  color: string;
}

/**
 * One swatch per line of the selected agencies. Bus networks get a single
 * entry (SamTrans has 75 routes), a rail agency's few buses (BART's bus
 * bridges) none, and a line that's split into one route per direction
 * (BART's Red-N and Red-S) shows once.
 */
export function legendEntries(
  routes: readonly Route[],
  agencies: ReadonlySet<AgencyId>,
  names: (id: AgencyId) => string = (id) => agencyName(id),
): LegendEntry[] {
  const out: LegendEntry[] = [];
  const seen = new Set<string>();
  const sorted = routes
    .filter((r) => agencies.has(r.agency))
    .sort((a, b) => compareAgencies(a.agency, b.agency));
  const hasRail = new Set(sorted.filter((r) => r.type !== 3).map((r) => r.agency));
  for (const r of sorted) {
    const bus = r.type === 3;
    if (bus && hasRail.has(r.agency)) continue;
    const label = bus ? `${names(r.agency)} buses` : (r.short_name || r.long_name || r.id).replace(/-[NS]$/, '');
    const key = bus ? `bus|${r.agency}` : `${r.agency}|${label}|${r.color}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({ label, color: r.color });
  }
  return out;
}
