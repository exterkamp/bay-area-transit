import { departures, stations } from '../../testing/fixtures';
import {
  findStation,
  groupByDirection,
  heading,
  indexById,
  mostCommon,
  sanitizePair,
  stationForPlatform,
  swapPair,
} from './stations';

describe('lookups', () => {
  it('indexes in API order', () => {
    const idx = indexById(stations);
    expect(idx.get('san_francisco')).toBe(0);
    expect(idx.get('college_park')).toBe(5);
  });

  it('finds by id and by platform id', () => {
    expect(findStation(stations, 'millbrae')?.name).toBe('Millbrae');
    expect(findStation(stations, '')).toBeUndefined();
    expect(stationForPlatform(stations, '70172')?.id).toBe('palo_alto');
    expect(stationForPlatform(stations, 'palo_alto')?.id).toBe('palo_alto');
    expect(stationForPlatform(stations, '99999')).toBeUndefined();
  });
});

describe('pairs', () => {
  it('swaps', () => {
    expect(swapPair({ from: 'a', to: 'b' })).toEqual({ from: 'b', to: 'a' });
  });

  it('drops unknown or duplicate ids from a remembered pair', () => {
    expect(sanitizePair(stations, { from: 'palo_alto', to: 'san_francisco' })).toEqual({
      from: 'palo_alto',
      to: 'san_francisco',
    });
    expect(sanitizePair(stations, { from: 'gone', to: 'millbrae' })).toEqual({ from: '', to: 'millbrae' });
    expect(sanitizePair(stations, { from: 'millbrae', to: 'millbrae' })).toEqual({ from: 'millbrae', to: '' });
    expect(sanitizePair(stations, null)).toEqual({ from: '', to: '' });
    expect(sanitizePair([], { from: 'millbrae', to: 'palo_alto' })).toEqual({ from: '', to: '' });
  });
});

describe('heading', () => {
  it('reads north/south from list order', () => {
    expect(heading(stations, 'palo_alto', 'san_francisco')).toBe('north');
    expect(heading(stations, 'palo_alto', 'san_jose_diridon')).toBe('south');
    expect(heading(stations, 'palo_alto', 'palo_alto')).toBeNull();
    expect(heading(stations, 'palo_alto', 'nowhere')).toBeNull();
  });
});

describe('groupByDirection', () => {
  it('splits by direction, northbound first, API order kept within', () => {
    const groups = groupByDirection(stations, 'palo_alto', departures);
    expect(groups.map((g) => g.label)).toEqual(['Northbound', 'Southbound']);
    expect(groups[0]!.departures.map((d) => d.trip_id)).toEqual(['401', '403']);
    expect(groups[1]!.departures.map((d) => d.trip_id)).toEqual(['402', '404']);
  });

  it('falls back to the headsign when the station is not on the ordered line', () => {
    const groups = groupByDirection([], 'palo_alto', departures);
    expect(groups.map((g) => g.label)).toEqual(['Toward San Francisco', 'Toward San Jose Diridon']);
  });

  it('is empty for an empty board', () => {
    expect(groupByDirection(stations, 'palo_alto', [])).toEqual([]);
  });
});

describe('mostCommon', () => {
  it('picks the most frequent, first on ties', () => {
    expect(mostCommon(['a', 'b', 'b'])).toBe('b');
    expect(mostCommon(['a', 'b'])).toBe('a');
    expect(mostCommon([])).toBe('');
  });
});
