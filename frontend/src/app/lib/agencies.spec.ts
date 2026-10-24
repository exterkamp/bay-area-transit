import { limited } from '../../testing/fixtures';
import { agencyName, compareAgencies, tripLabel, vehicleNoun } from './agencies';

describe('agencyName', () => {
  it('uses the name riders say', () => {
    expect(agencyName('SF', 'San Francisco Municipal Transportation Agency')).toBe('Muni');
    expect(agencyName('AC', 'AC Transit')).toBe('AC Transit');
    expect(agencyName('XX')).toBe('XX');
  });

  it('orders the four we care about first', () => {
    expect(['CT', 'ZZ', 'SF', 'BA', 'SM'].sort(compareAgencies)).toEqual(['SF', 'BA', 'SM', 'CT', 'ZZ']);
  });
});

describe('tripLabel', () => {
  it('numbers trips that have a number', () => {
    expect(tripLabel({ trip_id: 'CT:401', short_name: '401', route: limited })).toBe('Train 401');
  });

  it('drops a number that is only the trip id', () => {
    expect(tripLabel({ trip_id: 'SF:123', short_name: 'SF:123', route: { ...limited, type: 0 } })).toBe('Train');
    expect(tripLabel({ trip_id: 'SM:9', short_name: 'SM:9', route: { ...limited, type: 3 } })).toBe('Bus');
  });

  it('knows cable cars', () => {
    expect(vehicleNoun({ type: 5 })).toBe('Cable car');
    expect(vehicleNoun(null)).toBe('Train');
  });
});
