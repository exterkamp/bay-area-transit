import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { StateView } from '../shared/state';

@Component({
  selector: 'app-not-found',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, StateView],
  template: `
    <app-state kind="empty" title="Nothing at this stop" message="That page doesn't exist.">
      <a class="btn" routerLink="/">Plan a trip</a>
    </app-state>
  `,
})
export class NotFoundPage {}
