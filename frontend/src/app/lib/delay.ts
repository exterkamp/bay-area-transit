// Realtime delay helpers. Framework-free.

import type { StopTime } from '../api/models';

export interface DelayInfo {
  /** The time to plan around: the estimate when there is one, otherwise the schedule. */
  effective: string;
  /** True when there's a realtime estimate for this stop at all. */
  hasEstimate: boolean;
  /** Whole minutes late (negative = early), 0 when on time or without an estimate. */
  minutes: number;
  /** True when the estimate is at least a minute off the schedule, i.e. worth striking out the schedule. */
  changed: boolean;
  /** "+3 min", "2 min early", "On time", or "" without an estimate. */
  text: string;
}

/** Seconds of delay: the API's own figure when given, otherwise estimated − scheduled. */
export function delaySeconds(t: StopTime): number | null {
  if (t.delay_seconds != null) return t.delay_seconds;
  if (!t.estimated) return null;
  const d = (Date.parse(t.estimated) - Date.parse(t.scheduled)) / 1000;
  return Number.isNaN(d) ? null : d;
}

/** Delay text for a whole number of minutes. */
export function delayText(minutes: number): string {
  if (minutes > 0) return `+${minutes} min`;
  if (minutes < 0) return `${-minutes} min early`;
  return 'On time';
}

/** Epoch ms with the seconds dropped, i.e. the minute a rider sees on the clock. */
function displayedMinute(iso: string): number {
  const ms = Date.parse(iso);
  return Number.isNaN(ms) ? NaN : Math.floor(ms / 60_000) * 60_000;
}

export function delayInfo(t: StopTime): DelayInfo {
  if (!t.estimated) {
    return { effective: t.scheduled, hasEstimate: false, minutes: 0, changed: false, text: '' };
  }
  // Compare the minutes as displayed (h:mm), not the raw seconds: realtime
  // feeds report delays like 36 s, and "3:46 PM struck, 3:46 PM +1 min"
  // reads as nonsense. 3:46:00 -> 3:46:36 is on time; 1:37:50 -> 1:38:10
  // is +1 because the clock a rider reads changed.
  let minutes = Math.round((displayedMinute(t.estimated) - displayedMinute(t.scheduled)) / 60_000);
  if (Number.isNaN(minutes)) {
    const secs = delaySeconds(t);
    minutes = secs == null ? 0 : Math.round(secs / 60);
  }
  return {
    effective: t.estimated ?? t.scheduled,
    hasEstimate: true,
    minutes,
    changed: minutes !== 0,
    text: delayText(minutes),
  };
}

/** Severity bucket for styling delay text. */
export function delaySeverity(minutes: number): 'early' | 'ontime' | 'minor' | 'major' {
  if (minutes < 0) return 'early';
  if (minutes === 0) return 'ontime';
  if (minutes < 5) return 'minor';
  return 'major';
}
