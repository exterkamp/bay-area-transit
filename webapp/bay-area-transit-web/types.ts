export type Operator = {
    name: string;
    id: string;
}

export type Line = {
    name: string;
    id: string;
}

export enum StopType {
    Stop = 0,
    Station,
    Enter_Exit,
    Generic,
    Boarding,
  }

export type StopExtension = {
    type: StopType;
    parentStationId?: string;
}

export type Stop = {
    extensions?: StopExtension;
    id: string;
    name: string;
}

export type Direction = {
    id: string;
    name: string;
}

export type Pattern = {
    id: string;
    name: string;
    direction: Direction;
    stops: Stop[];
}

// export type CalendarTimetable = {}

// export type Timetable = {
//     calendar: CalendarTimetable;
//     timetable: 
// }