// Small display helpers. Framework-free.

import type { AgencyId, Alert, Fare } from '../api/models';
import { compareAgencies } from './agencies';

const HEX = /^#[0-9a-fA-F]{6}$/;

/** A #rrggbb color, or the contract's default when it's anything else. Safe to drop into a style. */
export function safeColor(c: string | null | undefined, fallback = '#888888'): string {
  return c && HEX.test(c) ? c : fallback;
}

/** "technical_problem" -> "Technical problem". */
export function humanizeEnum(v: string | null | undefined): string {
  if (!v) return '';
  const s = v.replace(/_/g, ' ').trim().toLowerCase();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** "Adult fare $8.50" - the API's fare is always the base adult fare. */
export function fareLabel(fare: Fare | null | undefined): string {
  const f = formatFare(fare);
  return f ? `Adult fare ${f}` : '';
}

/**
 * Station names as riders say them: the feed calls some stops "San
 * Francisco Caltrain Station" and others plain "Millbrae", so the trailing
 * "Caltrain Station" / "Station" goes.
 */
export function stationName(name: string | null | undefined): string {
  if (!name) return '';
  const short = name.replace(/\s+(?:Caltrain\s+)?Station$/i, '').trim();
  return short || name;
}

/** "$6.75". Falls back to "6.75 XYZ" for a currency Intl doesn't know. */
export function formatFare(fare: Fare | null | undefined): string {
  if (!fare) return '';
  const n = Number(fare.price);
  if (!Number.isFinite(n)) return '';
  try {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: fare.currency }).format(n);
  } catch {
    return `${fare.price} ${fare.currency}`;
  }
}

export function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/** "1 stop", "6 stops", "Nonstop". */
export function stopsText(n: number): string {
  if (n <= 0) return 'Nonstop';
  return n === 1 ? '1 stop' : `${n} stops`;
}

/** Alerts not yet dismissed, in API order. */
export function visibleAlerts(alerts: readonly Alert[], dismissed: ReadonlySet<string>): Alert[] {
  return alerts.filter((a) => !dismissed.has(a.id));
}

/**
 * Drop dismissed ids that no longer match an active alert so the stored
 * list doesn't grow forever. Only prune against a non-empty list: an empty
 * response may be a blip, and forgetting would resurface old alerts.
 */
export function pruneDismissed(dismissed: readonly string[], alerts: readonly Alert[]): string[] {
  if (alerts.length === 0) return [...dismissed];
  const live = new Set(alerts.map((a) => a.id));
  return dismissed.filter((id) => live.has(id));
}

/** Only http(s) links from an alert's url field; anything else is dropped. */
export function safeHttpUrl(u: string | null | undefined): string {
  if (!u) return '';
  try {
    const parsed = new URL(u);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:' ? parsed.href : '';
  } catch {
    return '';
  }
}

/** Normalize an ?op= value. Anything that doesn't look like a 511 code falls back. */
export function normalizeOperator(v: string | null | undefined, fallback = 'CT'): string {
  const s = (v ?? '').trim().toUpperCase();
  return /^[A-Z0-9]{1,8}$/.test(s) ? s : fallback;
}

/** "Muni, SF Bay Ferry": every agency a set of alerts is about, in agency order. */
export function alertAgencies(alerts: readonly Alert[], name: (id: AgencyId) => string): string {
  const ids = [...new Set(alerts.flatMap((a) => a.agencies ?? []))].sort(compareAgencies);
  return ids.map(name).join(', ');
}
