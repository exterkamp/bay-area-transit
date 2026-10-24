// URL builders for every endpoint in docs/api.md. Framework-free, so the
// resources that use them and the specs that test them agree on one spelling.

export const API_BASE = '/api/v1';

type Params = Record<string, string | number | null | undefined>;

export function withQuery(path: string, params: Params = {}): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === null || v === undefined || v === '') continue;
    q.set(k, String(v));
  }
  const s = q.toString();
  return s ? `${path}?${s}` : path;
}

const seg = encodeURIComponent;
const op = (code: string) => `${API_BASE}/operators/${seg(code)}`;

export const apiUrls = {
  health: () => '/healthz',
  operators: () => `${API_BASE}/operators`,
  agencies: (code: string) => `${op(code)}/agencies`,
  places: (code: string, p: { q?: string | null; near?: string | null; radius?: number; agency?: string | null; limit?: number }) =>
    withQuery(`${op(code)}/places`, { q: p.q, near: p.near, radius: p.radius, agency: p.agency, limit: p.limit }),
  place: (code: string, placeId: string) => `${op(code)}/places/${seg(placeId)}`,
  stations: (code: string, p: { agency?: string | null; route?: string | null } = {}) =>
    withQuery(`${op(code)}/stations`, { agency: p.agency, route: p.route }),
  routes: (code: string, p: { agency?: string | null } = {}) => withQuery(`${op(code)}/routes`, { agency: p.agency }),
  shapes: (code: string, p: { agency?: string | null } = {}) => withQuery(`${op(code)}/shapes`, { agency: p.agency }),
  plan: (code: string, p: { from: string; to: string; at?: string | null; limit?: number }) =>
    withQuery(`${op(code)}/plan`, { from: p.from, to: p.to, at: p.at, limit: p.limit }),
  departures: (code: string, stationId: string, p: { at?: string | null; limit?: number } = {}) =>
    withQuery(`${op(code)}/stations/${seg(stationId)}/departures`, { at: p.at, limit: p.limit }),
  trip: (code: string, tripId: string, date?: string | null) =>
    withQuery(`${op(code)}/trips/${seg(tripId)}`, { date }),
  vehicles: (code: string, p: { agency?: string | null } = {}) =>
    withQuery(`${op(code)}/vehicles`, { agency: p.agency }),
  alerts: (code: string) => `${op(code)}/alerts`,
};

/** The URL without one query param, to compare two requests that differ only in it. */
export function withoutParam(url: string, name: string): string {
  const [path, query = ''] = url.split('?', 2) as [string, string?];
  const q = new URLSearchParams(query);
  q.delete(name);
  const s = q.toString();
  return s ? `${path}?${s}` : path;
}
