import type { Route } from '../api/models';
import { legendEntries } from './legend';

const route = (id: string, agency: string, type: number, color = '#123456'): Route => ({
  id,
  short_name: id,
  long_name: '',
  type,
  color,
  text_color: '#ffffff',
  agency,
});

describe('legendEntries', () => {
  const routes = [
    route('ECR', 'SM', 3),
    route('Red-S', 'BA', 1, '#ff0000'),
    route('Red-N', 'BA', 1, '#ff0000'),
    route('N', 'SF', 0),
    route('292', 'SM', 3),
    route('Local', 'CT', 2),
    route('Bridge', 'BA', 3),
  ];

  it('keeps only selected agencies, Muni first', () => {
    expect(legendEntries(routes, new Set(['BA', 'SF'])).map((e) => e.label)).toEqual(['N', 'Red']);
  });

  it('leaves out a rail agency\'s buses', () => {
    expect(legendEntries(routes, new Set(['BA'])).map((e) => e.label)).toEqual(['Red']);
  });

  it('collapses a bus network to one entry', () => {
    expect(legendEntries(routes, new Set(['SM'])).map((e) => e.label)).toEqual(['SamTrans buses']);
  });
});
