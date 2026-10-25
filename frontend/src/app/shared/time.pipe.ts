import { Pipe, PipeTransform } from '@angular/core';
import { formatDate, formatServiceDate, formatTime } from '../lib/time';

/** `h:mm a` from the ISO string's own offset. */
@Pipe({ name: 'clock' })
export class ClockPipe implements PipeTransform {
  transform(iso: string | null | undefined): string {
    return formatTime(iso);
  }
}

/** "Jan 31, 2026". */
@Pipe({ name: 'day' })
export class DayPipe implements PipeTransform {
  transform(date: string | null | undefined): string {
    return formatDate(date);
  }
}

/** "Sat, Oct 24". */
@Pipe({ name: 'serviceDay' })
export class ServiceDayPipe implements PipeTransform {
  transform(date: string | null | undefined): string {
    return formatServiceDate(date);
  }
}
