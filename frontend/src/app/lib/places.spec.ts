import { dep, departures } from '../../testing/fixtures';
import { LEGACY_CALTRAIN_IDS, groupDepartures, legacyPairIds, readPair, topValues } from './places';

const a = { id: 'a', name: 'A', agencies: ['CT'] };
const b = { id: 'b', name: 'B', agencies: [] };

describe('readPair', () => {
  it('reads a stored pair', () => {
    expect(readPair({ from: a, to: b })).toEqual({ from: a, to: b });
  });

  it('turns junk into nulls', () => {
    expect(readPair(null)).toEqual({ from: null, to: null });
    expect(readPair({ from: 'palo_alto', to: { id: 3 } })).toEqual({ from: null, to: null });
    expect(readPair({ from: { id: 'a', name: 'A' } }).from?.agencies).toEqual([]);
  });

  it('never keeps the same place twice', () => {
    expect(readPair({ from: a, to: a })).toEqual({ from: a, to: null });
  });
});

describe('legacyPairIds', () => {
  it('maps renamed Caltrain ids and keeps the rest', () => {
    expect(legacyPairIds({ from: 'palo_alto', to: 'hillsdale' })).toEqual({
      from: LEGACY_CALTRAIN_IDS['palo_alto'],
      to: 'hillsdale',
    });
  });

  it('is null for nothing remembered', () => {
    expect(legacyPairIds(null)).toBeNull();
    expect(legacyPairIds({ from: '', to: 7 })).toBeNull();
  });
});

describe('groupDepartures', () => {
  it('names Caltrain directions, keeping time order within each', () => {
    const groups = groupDepartures(departures);
    expect(groups.map((g) => g.label)).toEqual(['Northbound', 'Southbound']);
    expect(groups[0]!.departures.map((d) => d.trip_id)).toEqual(['401', '403']);
    expect(groups[0]!.detail).toBe('to San Francisco');
  });

  it('splits by agency, Muni first, and falls back to headsigns', () => {
    const groups = groupDepartures([
      dep('b1', 0, ['rich', 'Richmond'], 'Richmond', { agency: 'BA' }),
      dep('m1', 1, ['emb', 'Embarcadero'], 'Embarcadero', { agency: 'SF' }),
      dep('b2', 0, ['ant', 'Antioch'], 'Antioch', { agency: 'BA' }),
      dep('b3', 0, ['rich', 'Richmond'], 'Richmond', { agency: 'BA' }),
    ]);
    expect(groups.map((g) => [g.agency, g.label])).toEqual([
      ['SF', 'Inbound'],
      ['BA', 'Toward Richmond · Antioch'],
    ]);
    expect(groups[1]!.detail).toBe('');
  });

  it('is empty for an empty board', () => {
    expect(groupDepartures([])).toEqual([]);
  });
});

describe('topValues', () => {
  it('orders by frequency, first seen on ties', () => {
    expect(topValues(['a', 'b', 'b', 'c', 'a', 'd'], 3)).toEqual(['a', 'b', 'c']);
  });
});
