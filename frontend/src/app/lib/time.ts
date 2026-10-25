// Time helpers. Framework-free.
//
// Every datetime the API sends carries the agency's own UTC offset, so the
// wall-clock time a rider should see is already written in the string. We
// format straight from those digits and never route through the browser's
// timezone: a phone set to New York still shows Caltrain times in Pacific.

const ISO_WALL = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?/;

export interface WallClock {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
}

/** The wall-clock fields written in an ISO string, ignoring its offset. */
export function wallClock(iso: string): WallClock | null {
  const m = ISO_WALL.exec(iso);
  if (!m) return null;
  return {
    year: Number(m[1]),
    month: Number(m[2]),
    day: Number(m[3]),
    hour: Number(m[4]),
    minute: Number(m[5]),
  };
}

/** `h:mm a`, e.g. "8:05 AM", from the ISO string's own wall time. "" when unparseable. */
export function formatTime(iso: string | null | undefined): string {
  if (!iso) return '';
  const w = wallClock(iso);
  if (!w) return '';
  const h12 = w.hour % 12 === 0 ? 12 : w.hour % 12;
  const ampm = w.hour < 12 ? 'AM' : 'PM';
  return `${h12}:${String(w.minute).padStart(2, '0')} ${ampm}`;
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

/** "Jan 31, 2026" from a YYYY-MM-DD (or the date part of an ISO datetime). */
export function formatDate(date: string | null | undefined): string {
  if (!date) return '';
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(date);
  if (!m) return '';
  const month = MONTHS[Number(m[2]) - 1];
  if (!month) return '';
  return `${month} ${Number(m[3])}, ${m[1]}`;
}

/** "Sat, Oct 24" from a YYYY-MM-DD. The weekday is calendar math, not timezone math. */
export function formatServiceDate(date: string | null | undefined): string {
  if (!date) return '';
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date);
  if (!m) return '';
  const y = Number(m[1]);
  const mo = Number(m[2]);
  const d = Number(m[3]);
  const weekday = WEEKDAYS[new Date(Date.UTC(y, mo - 1, d)).getUTCDay()];
  return `${weekday}, ${MONTHS[mo - 1]} ${d}`;
}

/** Whole minutes from `a` to `b` (both ISO), rounded. NaN if either is unparseable. */
export function minutesBetween(a: string, b: string): number {
  return Math.round((Date.parse(b) - Date.parse(a)) / 60_000);
}

/** "47 min", "1 hr 5 min". */
export function formatDuration(minutes: number): string {
  if (!Number.isFinite(minutes) || minutes < 0) return '';
  if (minutes < 60) return `${minutes} min`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m === 0 ? `${h} hr` : `${h} hr ${m} min`;
}

/**
 * Countdown text for a departure: "Now", "in 5 min", or "" once it's an hour
 * or more away (the clock time says enough by then) or already gone.
 */
export function countdown(iso: string, now: number): string {
  const ms = Date.parse(iso) - now;
  if (Number.isNaN(ms)) return '';
  const min = Math.floor(ms / 60_000);
  if (ms < -60_000) return '';
  if (min <= 0) return 'Now';
  if (min >= 60) return '';
  return `in ${min} min`;
}

/** "just now", "4 min ago", "2 hr ago". */
export function formatAge(iso: string, now: number): string {
  const ms = now - Date.parse(iso);
  if (Number.isNaN(ms)) return '';
  const min = Math.floor(ms / 60_000);
  if (min < 1) return 'just now';
  if (min < 60) return `${min} min ago`;
  const h = Math.floor(min / 60);
  if (h < 48) return `${h} hr ago`;
  return `${Math.floor(h / 24)} days ago`;
}

/**
 * The current wall-clock time in an IANA zone as `YYYY-MM-DDTHH:mm`, the
 * value format of <input type="datetime-local">. The API reads a naive `at`
 * in the agency's timezone, so this string can be sent as-is.
 */
export function nowInZone(timeZone: string, now: Date = new Date()): string {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(now);
  const get = (t: Intl.DateTimeFormatPartTypes) => parts.find((p) => p.type === t)?.value ?? '00';
  return `${get('year')}-${get('month')}-${get('day')}T${get('hour')}:${get('minute')}`;
}

/** Today's date in an IANA zone as YYYY-MM-DD. */
export function todayInZone(timeZone: string, now: Date = new Date()): string {
  return nowInZone(timeZone, now).slice(0, 10);
}

/** True if `date` (YYYY-MM-DD) falls in [start, end], all inclusive. String compare is safe for ISO dates. */
export function dateInRange(date: string, start: string, end: string): boolean {
  return date >= start && date <= end;
}

/** `h:mm a` for an instant (epoch ms) as seen in an IANA zone - for our own timestamps, not API ones. */
export function formatInstant(ms: number, timeZone: string): string {
  return formatTime(nowInZone(timeZone, new Date(ms)));
}
