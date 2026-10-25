import { KeyValueStore, readJson, STORAGE_KEYS, writeJson } from './storage';

function memoryStore(): KeyValueStore & { data: Map<string, string> } {
  const data = new Map<string, string>();
  return {
    data,
    getItem: (k) => data.get(k) ?? null,
    setItem: (k, v) => void data.set(k, v),
    removeItem: (k) => void data.delete(k),
  };
}

const throwing: KeyValueStore = {
  getItem: () => {
    throw new Error('SecurityError');
  },
  setItem: () => {
    throw new Error('QuotaExceededError');
  },
  removeItem: () => {
    throw new Error('SecurityError');
  },
};

describe('storage', () => {
  it('round-trips JSON', () => {
    const s = memoryStore();
    writeJson('k', { from: 'a', to: 'b' }, s);
    expect(readJson('k', null, s)).toEqual({ from: 'a', to: 'b' });
  });

  it('falls back on missing keys, junk, null stores and throwing stores', () => {
    const s = memoryStore();
    expect(readJson('missing', 7, s)).toBe(7);
    s.data.set('junk', '{not json');
    expect(readJson('junk', 'fb', s)).toBe('fb');
    expect(readJson('k', 'fb', null)).toBe('fb');
    expect(readJson('k', 'fb', throwing)).toBe('fb');
    expect(() => writeJson('k', 1, throwing)).not.toThrow();
    expect(() => writeJson('k', 1, null)).not.toThrow();
  });

  it('keys trips per operator', () => {
    expect(STORAGE_KEYS.trip('RG')).toBe('bat.trip2.RG');
    expect(STORAGE_KEYS.trip('BA')).not.toBe(STORAGE_KEYS.trip('CT'));
    // The old app's key is read for migration, never written: a new key, not a new shape in the old one.
    expect(STORAGE_KEYS.trip('CT')).not.toBe(STORAGE_KEYS.legacyTrip);
  });

  it('works with the default store when none exists (node)', () => {
    expect(readJson('anything', 'fb')).toBe('fb');
  });
});
