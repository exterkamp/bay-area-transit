import type { Agency, Place, Route, RouteRef } from '../api/models';
import { chooseScope, needsLine, readPlan, routeLabel, sortRoutes } from './plan-scope';

const agency = (id: string, places: number): Agency => ({
  id,
  name: id,
  url: '',
  timezone: 'America/Los_Angeles',
  route_types: [],
  feed: null,
  places,
});
const AGENCIES = [agency('SF', 257), agency('BA', 50), agency('SM', 1401), agency('CT', 30)];

const ref = (id: string, agency: string): RouteRef => ({ id, short_name: id, color: '', text_color: '', agency, type: 3 });
const place = (agencies: string[], routes: RouteRef[] = []): Pick<Place, 'agencies' | 'routes'> => ({ agencies, routes });

const millbrae = place(['BA', 'CT', 'SM'], [ref('SM:ECR', 'SM'), ref('SM:292', 'SM')]);
const paloAlto = place(['CT', 'SM'], [ref('SM:ECR', 'SM')]);
const powell = place(['BA', 'SF'], [ref('SF:F', 'SF')]);

describe('chooseScope', () => {
  const none = { agency: null, route: null };

  it('picks an agency serving both places, in the usual order', () => {
    expect(chooseScope(millbrae, powell, AGENCIES, none)).toEqual({ agency: 'BA', route: null });
  });

  it('keeps the preferred agency when it serves both', () => {
    expect(chooseScope(millbrae, paloAlto, AGENCIES, { agency: 'CT', route: null })).toEqual({ agency: 'CT', route: null });
  });

  it('picks a line serving both for an agency that needs one', () => {
    expect(chooseScope(millbrae, paloAlto, AGENCIES, { agency: 'SM', route: null })).toEqual({
      agency: 'SM',
      route: 'SM:ECR',
    });
  });

  it('prefers an agency that needs no line', () => {
    expect(chooseScope(powell, null, AGENCIES, none)).toEqual({ agency: 'BA', route: null });
  });

  it('falls back to the from place alone', () => {
    expect(chooseScope(powell, null, AGENCIES, { agency: 'SF', route: 'SF:N' })).toEqual({ agency: 'SF', route: 'SF:F' });
  });

  it('with no places, keeps a valid preference or starts on a whole-list agency', () => {
    expect(chooseScope(null, null, AGENCIES, { agency: 'SM', route: 'SM:ECR' })).toEqual({ agency: 'SM', route: 'SM:ECR' });
    expect(chooseScope(null, null, AGENCIES, { agency: 'ZZ', route: null })).toEqual({ agency: 'BA', route: null });
  });
});

describe('plan scope helpers', () => {
  it('needs a line only for big agencies', () => {
    expect(needsLine(agency('SM', 1401))).toBe(true);
    expect(needsLine(agency('BA', 50))).toBe(false);
    expect(needsLine(undefined)).toBe(false);
  });

  it('reads a remembered plan defensively', () => {
    expect(readPlan({ agency: 'BA', route: 7, from: 'a', to: 'a' })).toEqual({ agency: 'BA', route: null, from: 'a', to: '' });
    expect(readPlan(null)).toEqual({ agency: null, route: null, from: '', to: '' });
  });

  it('labels and sorts lines', () => {
    const r = (short_name: string, long_name = ''): Route => ({
      id: short_name,
      short_name,
      long_name,
      type: 3,
      color: '',
      text_color: '',
      agency: 'SM',
    });
    expect(routeLabel(r('ECR', 'El Camino Real'))).toBe('ECR · El Camino Real');
    expect(sortRoutes([r('ECR'), r('292'), r('10'), r('2')]).map((x) => x.short_name)).toEqual(['2', '10', '292', 'ECR']);
  });
});
