import { plan } from '../../testing/fixtures';
import { delayInfo, delaySeconds, delaySeverity, delayText } from './delay';

describe('delayText', () => {
  it('formats late, early and on time', () => {
    expect(delayText(3)).toBe('+3 min');
    expect(delayText(-2)).toBe('2 min early');
    expect(delayText(0)).toBe('On time');
  });
});

describe('delayInfo', () => {
  it('uses the estimate and the API delay', () => {
    const d = delayInfo(plan.trips[0]!.depart);
    expect(d).toEqual({
      effective: '2026-10-24T08:07:00-07:00',
      hasEstimate: true,
      minutes: 2,
      changed: true,
      text: '+2 min',
    });
  });

  it('falls back to the schedule without realtime', () => {
    const d = delayInfo(plan.trips[0]!.arrive);
    expect(d.effective).toBe('2026-10-24T08:52:00-07:00');
    expect(d.hasEstimate).toBe(false);
    expect(d.changed).toBe(false);
    expect(d.text).toBe('');
  });

  it('treats a sub-half-minute estimate as on time, not struck out', () => {
    const d = delayInfo({
      scheduled: '2026-10-24T08:05:00-07:00',
      estimated: '2026-10-24T08:05:20-07:00',
      delay_seconds: 20,
    });
    expect(d.changed).toBe(false);
    expect(d.text).toBe('On time');
  });

  it('compares displayed minutes, so a same-minute estimate is never struck out', () => {
    const same = delayInfo({
      scheduled: '2026-10-24T15:46:00-07:00',
      estimated: '2026-10-24T15:46:36-07:00',
      delay_seconds: 36,
    });
    expect(same.changed).toBe(false);
    expect(same.text).toBe('On time');
    const crossed = delayInfo({
      scheduled: '2026-10-24T13:37:00-07:00',
      estimated: '2026-10-24T13:38:10.5-07:00',
      delay_seconds: 70,
    });
    expect(crossed.changed).toBe(true);
    expect(crossed.text).toBe('+1 min');
  });

  it('derives the delay from the times when delay_seconds is missing', () => {
    const t = {
      scheduled: '2026-10-24T08:05:00-07:00',
      estimated: '2026-10-24T15:09:00Z',
      delay_seconds: null,
    };
    expect(delaySeconds(t)).toBe(240);
    expect(delayInfo(t).text).toBe('+4 min');
  });

  it('reports early trains', () => {
    const d = delayInfo({
      scheduled: '2026-10-24T08:05:00-07:00',
      estimated: '2026-10-24T08:04:00-07:00',
      delay_seconds: -60,
    });
    expect(d.minutes).toBe(-1);
    expect(d.text).toBe('1 min early');
  });

  it('ignores delay_seconds when there is no estimate', () => {
    const d = delayInfo({ scheduled: '2026-10-24T08:05:00-07:00', estimated: null, delay_seconds: 300 });
    expect(d.hasEstimate).toBe(false);
  });
});

describe('delaySeverity', () => {
  it('buckets', () => {
    expect(delaySeverity(-1)).toBe('early');
    expect(delaySeverity(0)).toBe('ontime');
    expect(delaySeverity(3)).toBe('minor');
    expect(delaySeverity(5)).toBe('major');
  });
});
