import {
  countdown,
  dateInRange,
  formatAge,
  formatDate,
  formatDuration,
  formatInstant,
  formatServiceDate,
  formatTime,
  minutesBetween,
  nowInZone,
  todayInZone,
  wallClock,
} from './time';

describe('formatTime', () => {
  it('formats from the string own wall time, not the browser zone', () => {
    expect(formatTime('2026-10-24T08:05:00-07:00')).toBe('8:05 AM');
    // Same instant written in UTC reads differently - by design, the API sends agency offsets.
    expect(formatTime('2026-10-24T15:05:00+00:00')).toBe('3:05 PM');
  });

  it('handles noon, midnight and evening', () => {
    expect(formatTime('2026-10-24T00:00:00-07:00')).toBe('12:00 AM');
    expect(formatTime('2026-10-24T12:30:00-07:00')).toBe('12:30 PM');
    expect(formatTime('2026-10-24T23:59:00-07:00')).toBe('11:59 PM');
  });

  it('accepts Z, fractional seconds and no seconds', () => {
    expect(formatTime('2026-10-24T08:05:30.123Z')).toBe('8:05 AM');
    expect(formatTime('2026-10-24T18:05-07:00')).toBe('6:05 PM');
  });

  it('returns "" for null or junk', () => {
    expect(formatTime(null)).toBe('');
    expect(formatTime(undefined)).toBe('');
    expect(formatTime('not a time')).toBe('');
  });
});

describe('wallClock', () => {
  it('reads the fields', () => {
    expect(wallClock('2026-10-24T08:05:00-07:00')).toEqual({
      year: 2026,
      month: 10,
      day: 24,
      hour: 8,
      minute: 5,
    });
    expect(wallClock('2026-10-24')).toBeNull();
  });
});

describe('dates', () => {
  it('formatDate', () => {
    expect(formatDate('2026-01-31')).toBe('Jan 31, 2026');
    expect(formatDate('2027-12-01T00:00:00-08:00')).toBe('Dec 1, 2027');
    expect(formatDate('2026-13-01')).toBe('');
    expect(formatDate(null)).toBe('');
  });

  it('formatServiceDate includes the weekday', () => {
    expect(formatServiceDate('2026-10-24')).toBe('Sat, Oct 24');
    expect(formatServiceDate('2026-10-26')).toBe('Mon, Oct 26');
    expect(formatServiceDate('garbage')).toBe('');
  });

  it('dateInRange is inclusive', () => {
    expect(dateInRange('2026-01-31', '2026-01-31', '2027-01-31')).toBe(true);
    expect(dateInRange('2027-01-31', '2026-01-31', '2027-01-31')).toBe(true);
    expect(dateInRange('2027-02-01', '2026-01-31', '2027-01-31')).toBe(false);
  });
});

describe('durations', () => {
  it('minutesBetween respects offsets', () => {
    expect(minutesBetween('2026-10-24T08:05:00-07:00', '2026-10-24T08:52:00-07:00')).toBe(47);
    expect(minutesBetween('2026-10-24T08:00:00-07:00', '2026-10-24T15:30:00Z')).toBe(30);
  });

  it('formatDuration', () => {
    expect(formatDuration(47)).toBe('47 min');
    expect(formatDuration(60)).toBe('1 hr');
    expect(formatDuration(65)).toBe('1 hr 5 min');
    expect(formatDuration(-1)).toBe('');
  });
});

describe('countdown', () => {
  const t = '2026-10-24T08:10:00-07:00';
  const at = (iso: string) => Date.parse(iso);

  it('says Now within the minute either side', () => {
    expect(countdown(t, at('2026-10-24T08:09:30-07:00'))).toBe('Now');
    expect(countdown(t, at('2026-10-24T08:10:30-07:00'))).toBe('Now');
  });

  it('counts whole minutes down', () => {
    expect(countdown(t, at('2026-10-24T08:05:00-07:00'))).toBe('in 5 min');
    expect(countdown(t, at('2026-10-24T08:05:30-07:00'))).toBe('in 4 min');
  });

  it('is blank for long-gone or an hour+ away', () => {
    expect(countdown(t, at('2026-10-24T08:15:00-07:00'))).toBe('');
    expect(countdown(t, at('2026-10-24T07:00:00-07:00'))).toBe('');
  });
});

describe('formatAge', () => {
  const now = Date.parse('2026-10-24T08:20:00-07:00');
  it('reads naturally', () => {
    expect(formatAge('2026-10-24T08:19:40-07:00', now)).toBe('just now');
    expect(formatAge('2026-10-24T08:06:00-07:00', now)).toBe('14 min ago');
    expect(formatAge('2026-10-24T05:20:00-07:00', now)).toBe('3 hr ago');
    expect(formatAge('2026-10-20T08:20:00-07:00', now)).toBe('4 days ago');
  });
});

describe('nowInZone', () => {
  it('gives agency wall time regardless of host zone', () => {
    const instant = new Date('2026-10-24T15:05:00Z');
    expect(nowInZone('America/Los_Angeles', instant)).toBe('2026-10-24T08:05');
    expect(nowInZone('America/New_York', instant)).toBe('2026-10-24T11:05');
  });

  it('handles the date rollover and midnight as 00 not 24', () => {
    const instant = new Date('2026-10-25T07:00:00Z');
    expect(nowInZone('America/Los_Angeles', instant)).toBe('2026-10-25T00:00');
    expect(todayInZone('America/Los_Angeles', new Date('2026-10-25T06:59:00Z'))).toBe('2026-10-24');
  });
});

describe('formatInstant', () => {
  it('formats epoch ms in the agency zone', () => {
    expect(formatInstant(Date.parse('2026-10-24T15:05:00Z'), 'America/Los_Angeles')).toBe('8:05 AM');
  });
});
