import { alert } from '../../testing/fixtures';
import {
  escapeHtml,
  fareLabel,
  formatFare,
  humanizeEnum,
  normalizeOperator,
  pruneDismissed,
  safeColor,
  safeHttpUrl,
  stationName,
  stopsText,
  visibleAlerts,
} from './format';

describe('format helpers', () => {
  it('safeColor only passes #rrggbb', () => {
    expect(safeColor('#99d7dc')).toBe('#99d7dc');
    expect(safeColor('red')).toBe('#888888');
    expect(safeColor('#fff')).toBe('#888888');
    expect(safeColor('#000000;background:url(x)')).toBe('#888888');
    expect(safeColor(null, '#000000')).toBe('#000000');
  });

  it('humanizeEnum', () => {
    expect(humanizeEnum('technical_problem')).toBe('Technical problem');
    expect(humanizeEnum('SIGNIFICANT_DELAYS')).toBe('Significant delays');
    expect(humanizeEnum('')).toBe('');
  });

  it('formatFare', () => {
    expect(formatFare({ price: '6.75', currency: 'USD' })).toBe('$6.75');
    expect(formatFare({ price: '6.75', currency: 'NOPE' })).toBe('6.75 NOPE');
    expect(formatFare({ price: 'x', currency: 'USD' })).toBe('');
    expect(formatFare(null)).toBe('');
  });

  it('escapeHtml', () => {
    expect(escapeHtml(`<b a="1">'&'</b>`)).toBe('&lt;b a=&quot;1&quot;&gt;&#39;&amp;&#39;&lt;/b&gt;');
  });

  it('stopsText', () => {
    expect(stopsText(0)).toBe('Nonstop');
    expect(stopsText(1)).toBe('1 stop');
    expect(stopsText(6)).toBe('6 stops');
  });

  it('safeHttpUrl', () => {
    expect(safeHttpUrl('https://www.caltrain.com/alerts')).toBe('https://www.caltrain.com/alerts');
    expect(safeHttpUrl('javascript:alert(1)')).toBe('');
    expect(safeHttpUrl('')).toBe('');
    expect(safeHttpUrl('not a url')).toBe('');
  });

  it('normalizeOperator', () => {
    expect(normalizeOperator('ba')).toBe('BA');
    expect(normalizeOperator(null)).toBe('CT');
    expect(normalizeOperator('../x')).toBe('CT');
  });
});

describe('alert dismissal', () => {
  const other = { ...alert, id: 'alert-456' };

  it('hides dismissed alerts', () => {
    expect(visibleAlerts([alert, other], new Set(['alert-123']))).toEqual([other]);
  });

  it('prunes ids of alerts that ended, but not on an empty list', () => {
    expect(pruneDismissed(['alert-123', 'old'], [alert])).toEqual(['alert-123']);
    expect(pruneDismissed(['alert-123'], [])).toEqual(['alert-123']);
  });
});

describe('fareLabel and stationName', () => {
  it('labels the adult fare', () => {
    expect(fareLabel({ price: '8.50', currency: 'USD' })).toBe('Adult fare $8.50');
    expect(fareLabel(null)).toBe('');
  });

  it('drops the Caltrain Station suffix', () => {
    expect(stationName('San Francisco Caltrain Station')).toBe('San Francisco');
    expect(stationName('Tamien Caltrain Station')).toBe('Tamien');
    expect(stationName('Millbrae')).toBe('Millbrae');
    expect(stationName('Station')).toBe('Station');
    expect(stationName(null)).toBe('');
  });
});
