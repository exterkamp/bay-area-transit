import { operatorCT } from '../../testing/fixtures';
import { freshness, realtimeLabel, summarizeRealtime, type RealtimeSummary } from './staleness';
import { formatTime } from './time';

const at = (iso: string) => Date.parse(iso);

describe('freshness', () => {
  it('is unavailable for null or junk', () => {
    expect(freshness(null, Date.now())).toBe('unavailable');
    expect(freshness('nope', Date.now())).toBe('unavailable');
  });

  it('flips to stale after 10 minutes', () => {
    const t = '2026-10-24T08:14:00-07:00';
    expect(freshness(t, at('2026-10-24T08:24:00-07:00'))).toBe('fresh');
    expect(freshness(t, at('2026-10-24T08:24:01-07:00'))).toBe('stale');
  });
});

describe('summarizeRealtime', () => {
  it('is fresh when trip updates and vehicles are recent', () => {
    const s = summarizeRealtime(operatorCT.realtime, at('2026-10-24T08:15:00-07:00'));
    expect(s.status).toBe('fresh');
    expect(s.latest).toBe('2026-10-24T08:14:05-07:00');
  });

  it('is stale when either counted feed is old', () => {
    const s = summarizeRealtime(operatorCT.realtime, at('2026-10-24T08:40:00-07:00'));
    expect(s.status).toBe('stale');
  });

  it('is stale when one counted feed has never polled', () => {
    const s = summarizeRealtime(
      { ...operatorCT.realtime, vehicle_positions_at: null },
      at('2026-10-24T08:15:00-07:00'),
    );
    expect(s.status).toBe('stale');
    expect(s.vehiclePositions).toBe('unavailable');
  });

  it('is unavailable when no counted feed has ever polled', () => {
    const s = summarizeRealtime(
      { trip_updates_at: null, vehicle_positions_at: null, alerts_at: '2026-10-24T08:10:00-07:00' },
      at('2026-10-24T08:15:00-07:00'),
    );
    expect(s.status).toBe('unavailable');
    expect(s.latest).toBeNull();
  });

  it('does not let an old alerts poll flip the indicator', () => {
    const s = summarizeRealtime(
      { ...operatorCT.realtime, alerts_at: '2026-10-24T01:00:00-07:00' },
      at('2026-10-24T08:15:00-07:00'),
    );
    expect(s.status).toBe('fresh');
    expect(s.alerts).toBe('stale');
  });

  it('copes with a missing realtime block', () => {
    expect(summarizeRealtime(undefined, Date.now()).status).toBe('unavailable');
  });
});

describe('realtimeLabel', () => {
  const summary = (status: RealtimeSummary['status'], latest: string | null): RealtimeSummary => ({
    status,
    latest,
    tripUpdates: status,
    vehiclePositions: status,
    alerts: status,
  });

  it('shows when fresh data was fetched, in the agency clock', () => {
    expect(realtimeLabel(summary('fresh', '2026-10-24T13:36:05-07:00'), formatTime)).toBe('Updated 1:36 PM');
  });

  it('flags stale data but still says when it was fetched', () => {
    expect(realtimeLabel(summary('stale', '2026-10-24T13:36:05-07:00'), formatTime)).toBe(
      'Delayed · updated 1:36 PM',
    );
  });

  it('falls back when there is nothing to date', () => {
    expect(realtimeLabel(summary('unavailable', null), formatTime)).toBe('Schedule only');
    expect(realtimeLabel(summary('stale', null), formatTime)).toBe('Live data delayed');
  });
});
