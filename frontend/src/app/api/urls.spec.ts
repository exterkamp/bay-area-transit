import { apiUrls, withoutParam, withQuery } from './urls';

describe('apiUrls', () => {
  it('builds operator-scoped paths', () => {
    expect(apiUrls.operators()).toBe('/api/v1/operators');
    expect(apiUrls.stations('CT')).toBe('/api/v1/operators/CT/stations');
    expect(apiUrls.shapes('CT')).toBe('/api/v1/operators/CT/shapes');
    expect(apiUrls.vehicles('CT')).toBe('/api/v1/operators/CT/vehicles');
    expect(apiUrls.alerts('CT')).toBe('/api/v1/operators/CT/alerts');
  });

  it('omits at when leaving now', () => {
    expect(apiUrls.plan('CT', { from: 'palo_alto', to: 'san_francisco', limit: 10 })).toBe(
      '/api/v1/operators/CT/plan?from=palo_alto&to=san_francisco&limit=10',
    );
    expect(apiUrls.plan('CT', { from: 'a', to: 'b', at: '2026-10-24T08:00' })).toBe(
      '/api/v1/operators/CT/plan?from=a&to=b&at=2026-10-24T08%3A00',
    );
  });

  it('encodes path segments', () => {
    expect(apiUrls.departures('CT', 'a/b', { limit: 20 })).toBe(
      '/api/v1/operators/CT/stations/a%2Fb/departures?limit=20',
    );
    expect(apiUrls.trip('CT', '401', '2026-10-24')).toBe('/api/v1/operators/CT/trips/401?date=2026-10-24');
    expect(apiUrls.trip('CT', '401')).toBe('/api/v1/operators/CT/trips/401');
  });

  it('withQuery drops empty values', () => {
    expect(withQuery('/x', { a: '', b: null, c: undefined })).toBe('/x');
  });
});

describe('withoutParam', () => {
  it('removes just that param', () => {
    expect(withoutParam('/p?from=a&to=b&limit=20', 'limit')).toBe('/p?from=a&to=b');
    expect(withoutParam('/p?limit=20', 'limit')).toBe('/p');
    expect(withoutParam('/p', 'limit')).toBe('/p');
  });
});
