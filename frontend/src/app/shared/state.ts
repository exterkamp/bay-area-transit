import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/** Loading, error and empty states, all in one calm box. Project actions as content. */
@Component({
  selector: 'app-state',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { '[attr.data-kind]': 'kind()', role: 'status', '[attr.aria-busy]': "kind() === 'loading'" },
  template: `
    @if (kind() === 'loading') {
      <span class="spinner" aria-hidden="true"></span>
      <p class="title">{{ title() || 'Loading…' }}</p>
    } @else {
      <p class="title">{{ title() }}</p>
      @if (message()) {
        <p class="msg">{{ message() }}</p>
      }
    }
    <ng-content />
  `,
  styles: `
    :host {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 0.4rem;
      text-align: center;
      padding: 2rem 1rem;
      color: var(--muted);
    }
    :host([data-kind='error']) .title { color: var(--bad); }
    .title { margin: 0; font-weight: 600; color: var(--fg); }
    .msg { margin: 0; max-width: 32ch; font-size: 0.9rem; }
    .spinner {
      width: 1.4rem;
      height: 1.4rem;
      border-radius: 50%;
      border: 2px solid var(--line);
      border-top-color: var(--accent);
      animation: spin 0.8s linear infinite;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    @media (prefers-reduced-motion: reduce) { .spinner { animation-duration: 3s; } }
  `,
})
export class StateView {
  readonly kind = input<'loading' | 'error' | 'empty'>('loading');
  readonly title = input('');
  readonly message = input('');
}
