// Realtime freshness. Framework-free.
//
// docs/api.md: any realtime.*_at is null when that feed has never been
// polled; a value older than ~10 minutes means realtime is stale.

import type { RealtimeInfo } from '../api/models';

export const STALE_AFTER_MS = 10 * 60_000;

export type FeedFreshness = 'fresh' | 'stale' | 'unavailable';

export function freshness(at: string | null | undefined, now: number): FeedFreshness {
  if (!at) return 'unavailable';
  const t = Date.parse(at);
  if (Number.isNaN(t)) return 'unavailable';
  return now - t > STALE_AFTER_MS ? 'stale' : 'fresh';
}

export interface RealtimeSummary {
  status: FeedFreshness;
  /** The most recent poll among the feeds that count, or null. */
  latest: string | null;
  tripUpdates: FeedFreshness;
  vehiclePositions: FeedFreshness;
  alerts: FeedFreshness;
}

const RANK: Record<FeedFreshness, number> = { fresh: 0, stale: 1, unavailable: 2 };

/**
 * One status for the header indicator. It is driven by trip updates and
 * vehicle positions - the feeds that change the times and dots a rider
 * sees. Alerts are reported per-feed but don't flip the indicator, since an
 * agency can go a long while without publishing one.
 *
 * - all counted feeds unavailable -> unavailable
 * - any counted feed stale or unavailable -> stale
 * - otherwise fresh
 */
export function summarizeRealtime(rt: RealtimeInfo | null | undefined, now: number): RealtimeSummary {
  const tripUpdates = freshness(rt?.trip_updates_at, now);
  const vehiclePositions = freshness(rt?.vehicle_positions_at, now);
  const alerts = freshness(rt?.alerts_at, now);
  const counted = [tripUpdates, vehiclePositions];
  let status: FeedFreshness;
  if (counted.every((s) => s === 'unavailable')) status = 'unavailable';
  else if (counted.some((s) => RANK[s] > 0)) status = 'stale';
  else status = 'fresh';

  const stamps = [rt?.trip_updates_at, rt?.vehicle_positions_at]
    .filter((s): s is string => !!s && !Number.isNaN(Date.parse(s)))
    .sort((a, b) => Date.parse(b) - Date.parse(a));
  return { status, latest: stamps[0] ?? null, tripUpdates, vehiclePositions, alerts };
}

/**
 * The header pill's text: when live data was last fetched, as agency
 * wall-clock time ("Updated 1:36 PM"), so a rider can judge it at a glance.
 */
export function realtimeLabel(summary: RealtimeSummary, formatTime: (iso: string) => string): string {
  if (summary.status === 'unavailable' || !summary.latest) {
    return summary.status === 'stale' ? 'Live data delayed' : 'Schedule only';
  }
  const at = formatTime(summary.latest);
  return summary.status === 'fresh' ? `Updated ${at}` : `Delayed · updated ${at}`;
}
