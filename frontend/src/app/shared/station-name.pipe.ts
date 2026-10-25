import { Pipe, PipeTransform } from '@angular/core';
import { stationName } from '../lib/format';

/** "San Francisco Caltrain Station" -> "San Francisco". */
@Pipe({ name: 'stationName' })
export class StationNamePipe implements PipeTransform {
  transform(name: string | null | undefined): string {
    return stationName(name);
  }
}
