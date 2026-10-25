import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    pathMatch: 'full',
    title: 'Trip planner · Bay Area Transit',
    loadComponent: () => import('./pages/planner/planner-page').then((m) => m.PlannerPage),
  },
  {
    path: 'stations/:id',
    title: 'Departures · Bay Area Transit',
    loadComponent: () => import('./pages/station/station-page').then((m) => m.StationPage),
  },
  {
    path: 'trips/:tripId',
    title: 'Trip · Bay Area Transit',
    loadComponent: () => import('./pages/trip/trip-page').then((m) => m.TripPage),
  },
  {
    path: 'map',
    title: 'Map · Bay Area Transit',
    data: { fullBleed: true },
    loadComponent: () => import('./pages/map/map-page').then((m) => m.MapPage),
  },
  {
    path: '**',
    title: 'Not found · Bay Area Transit',
    loadComponent: () => import('./pages/not-found').then((m) => m.NotFoundPage),
  },
];
