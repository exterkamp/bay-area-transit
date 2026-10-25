import { httpResource } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  ElementRef,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';
import type { Place, PlaceSearch } from '../api/models';
import { apiUrls } from '../api/urls';
import { OperatorService } from '../core/operator.service';
import { stationName } from '../lib/format';
import { PlaceRef, formatDistance, placeRef } from '../lib/places';
import { AgencyChips } from './agency-chips';
import { RouteBadge } from './route-badge';

const MIN_CHARS = 2;
const DEBOUNCE_MS = 180;
const LIMIT = 8;
const NEAR_RADIUS = 1500;

let nextId = 0;

interface Option {
  ref: PlaceRef;
  place: Place | null;
}

/**
 * Search-as-you-type place picker, an ARIA 1.2 combobox. Empty, it offers
 * the recent picks and (where the browser allows it) places near you.
 */
@Component({
  selector: 'app-place-picker',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [AgencyChips, RouteBadge],
  templateUrl: './place-picker.html',
  styleUrl: './place-picker.scss',
  host: { '(focusout)': 'onFocusOut($event)' },
})
export class PlacePicker {
  private readonly op = inject(OperatorService);
  private readonly host = inject(ElementRef<HTMLElement>);

  readonly label = input.required<string>();
  readonly value = input<PlaceRef | null>(null);
  readonly recents = input<readonly PlaceRef[]>([]);
  readonly placeholder = input('Search stations and stops');
  readonly picked = output<PlaceRef>();

  protected readonly id = `place-${nextId++}`;
  private readonly inputEl = viewChild.required<ElementRef<HTMLInputElement>>('field');

  protected readonly query = signal('');
  protected readonly editing = signal(false);
  protected readonly open = signal(false);
  protected readonly active = signal(-1);
  private readonly settled = signal('');
  protected readonly near = signal<string | null>(null);
  protected readonly locating = signal(false);
  protected readonly locateError = signal('');

  protected readonly canLocate =
    typeof window !== 'undefined' && window.isSecureContext && 'geolocation' in navigator;

  private readonly search = httpResource<PlaceSearch>(() => {
    if (this.op.noFeed()) return undefined;
    const q = this.settled().trim();
    const near = this.near();
    if (q.length >= MIN_CHARS) return apiUrls.places(this.op.code(), { q, limit: LIMIT });
    if (near && !q) return apiUrls.places(this.op.code(), { near, radius: NEAR_RADIUS, limit: LIMIT });
    return undefined;
  });

  protected readonly searching = computed(() => this.query().trim().length >= MIN_CHARS);
  protected readonly showingNearby = computed(() => !this.searching() && !!this.near());

  protected readonly options = computed<Option[]>(() => {
    if (this.searching() || this.showingNearby()) {
      return (this.search.hasValue() ? this.search.value().places : []).map((p) => ({ ref: placeRef(p), place: p }));
    }
    return this.recents()
      .filter((r) => r.id !== this.value()?.id)
      .map((ref) => ({ ref, place: null }));
  });

  protected readonly loading = computed(() => this.search.isLoading() && (this.searching() || this.showingNearby()));
  protected readonly failed = computed(() => this.search.status() === 'error');

  protected readonly display = computed(() =>
    this.editing() ? this.query() : stationName(this.value()?.name ?? ''),
  );

  constructor() {
    let timer: ReturnType<typeof setTimeout> | undefined;
    effect(() => {
      const q = this.query();
      clearTimeout(timer);
      timer = setTimeout(() => this.settled.set(q), DEBOUNCE_MS);
    });
    inject(DestroyRef).onDestroy(() => clearTimeout(timer));
    // A new result list starts with nothing highlighted.
    effect(() => {
      this.options();
      this.active.set(-1);
    });
  }

  protected optionId(i: number): string {
    return `${this.id}-opt-${i}`;
  }

  protected onFocus(): void {
    this.editing.set(true);
    this.query.set('');
    this.open.set(true);
  }

  protected onInput(value: string): void {
    this.query.set(value);
    this.open.set(true);
  }

  protected onKeydown(e: KeyboardEvent): void {
    const n = this.options().length;
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        this.open.set(true);
        if (n) this.active.update((i) => (i + 1) % n);
        break;
      case 'ArrowUp':
        e.preventDefault();
        if (n) this.active.update((i) => (i <= 0 ? n - 1 : i - 1));
        break;
      case 'Enter': {
        const opt = this.options()[this.active() >= 0 ? this.active() : 0];
        if (this.open() && opt && (this.active() >= 0 || this.searching())) {
          e.preventDefault();
          this.choose(opt.ref);
        }
        break;
      }
      case 'Escape':
        if (this.open()) {
          e.preventDefault();
          this.close();
        }
        break;
    }
  }

  protected onFocusOut(e: FocusEvent): void {
    const next = e.relatedTarget as Node | null;
    if (next && this.host.nativeElement.contains(next)) return;
    this.close();
  }

  protected choose(ref: PlaceRef): void {
    this.picked.emit(ref);
    this.close();
    this.inputEl().nativeElement.blur();
  }

  protected locate(): void {
    if (!this.canLocate) return;
    this.locating.set(true);
    this.locateError.set('');
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        this.locating.set(false);
        this.near.set(`${pos.coords.latitude.toFixed(5)},${pos.coords.longitude.toFixed(5)}`);
        this.inputEl().nativeElement.focus();
      },
      (err) => {
        this.locating.set(false);
        this.locateError.set(err.code === err.PERMISSION_DENIED ? 'Location is turned off for this site.' : "Couldn't find your location.");
      },
      { enableHighAccuracy: false, timeout: 10_000, maximumAge: 60_000 },
    );
  }

  private close(): void {
    this.open.set(false);
    this.editing.set(false);
    this.query.set('');
    this.active.set(-1);
  }

  protected readonly stationName = stationName;
  protected readonly formatDistance = formatDistance;
}
