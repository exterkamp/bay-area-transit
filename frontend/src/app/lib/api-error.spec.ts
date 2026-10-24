import { classifyError, errorCode, errorDetail } from './api-error';

describe('classifyError', () => {
  it('spots the no-active-feed 404', () => {
    expect(classifyError({ status: 404, error: { detail: 'Operator CT has no active feed' } }).kind).toBe(
      'no-feed',
    );
  });

  it('treats other 404s as not found, with the detail', () => {
    const v = classifyError({ status: 404, error: { detail: 'Unknown station: nope' } }, 'that station');
    expect(v.kind).toBe('not-found');
    expect(v.title).toBe("Couldn't find that station");
    expect(v.message).toBe('Unknown station: nope');
  });

  it('400, offline and 5xx', () => {
    expect(classifyError({ status: 400, error: { detail: 'from == to' } }).message).toBe('from == to');
    expect(classifyError({ status: 0, error: { type: 'error' } }).kind).toBe('offline');
    expect(classifyError({ status: 502, error: '<html>' }).kind).toBe('offline');
    expect(classifyError({ status: 500, error: '<html>' }).kind).toBe('server');
  });

  it('errorDetail tolerates odd bodies', () => {
    expect(errorDetail(null)).toBe('');
    expect(errorDetail({ error: 'text' })).toBe('');
    expect(errorDetail({ error: { detail: 3 } })).toBe('');
  });
});

describe('classifyError by code', () => {
  it('trusts code over detail text', () => {
    expect(classifyError({ status: 404, error: { detail: 'whatever', code: 'no_active_feed' } }).kind).toBe('no-feed');
    expect(classifyError({ status: 404, error: { detail: 'no feed here', code: 'not_found' } }).kind).toBe('not-found');
    expect(
      classifyError({ status: 400, error: { detail: 'from and to must be different stations', code: 'bad_request' } })
        .kind,
    ).toBe('bad-request');
  });

  it('reads the real backend body', () => {
    const v = classifyError({ status: 404, error: { detail: "unknown station 'nope'", code: 'not_found' } }, 'that station');
    expect(v.kind).toBe('not-found');
    expect(errorCode({ error: { code: 'not_found' } })).toBe('not_found');
    expect(errorCode({ error: '<html>' })).toBe('');
  });
});
