// Turning a failed request into something a rider can read. Framework-free:
// takes anything shaped like an HttpErrorResponse.

export type ApiErrorKind = 'no-feed' | 'not-found' | 'bad-request' | 'offline' | 'server';

export interface ApiErrorView {
  kind: ApiErrorKind;
  title: string;
  message: string;
}

interface ErrorLike {
  status?: number;
  error?: unknown;
}

export function errorCode(err: unknown): string {
  const body = (err as ErrorLike | null)?.error;
  if (body && typeof body === 'object' && 'code' in body) {
    const c = (body as { code: unknown }).code;
    if (typeof c === 'string') return c;
  }
  return '';
}

export function errorDetail(err: unknown): string {
  const body = (err as ErrorLike | null)?.error;
  if (body && typeof body === 'object' && 'detail' in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === 'string') return d;
  }
  return '';
}

/**
 * Errors carry `code` (no_active_feed | not_found | bad_request). Only when
 * a body has no code (an older backend, or a proxy's own error page) do we
 * fall back to the status, and to the word "feed" in the detail.
 */
export function classifyError(err: unknown, what = 'that'): ApiErrorView {
  const status = (err as ErrorLike | null)?.status ?? 0;
  const detail = errorDetail(err);
  const code = errorCode(err);
  const noFeed = code ? code === 'no_active_feed' : status === 404 && /\bfeed\b/i.test(detail);
  const notFound = code ? code === 'not_found' : status === 404;
  const badRequest = code ? code === 'bad_request' : status === 400;
  if (noFeed) {
    return {
      kind: 'no-feed',
      title: 'No schedule loaded yet',
      message: "The timetable for this operator hasn't been imported. Check back soon.",
    };
  }
  if (notFound) {
    return { kind: 'not-found', title: `Couldn't find ${what}`, message: detail || 'It may not run on that day.' };
  }
  if (badRequest) {
    return { kind: 'bad-request', title: 'Check your search', message: detail || 'Something about that request was off.' };
  }
  if (status === 0 || status === 502 || status === 503 || status === 504) {
    return {
      kind: 'offline',
      title: "Can't reach the server",
      message: 'You may be offline, or the service is restarting.',
    };
  }
  return { kind: 'server', title: 'Something went wrong', message: detail || `The server answered ${status}.` };
}
