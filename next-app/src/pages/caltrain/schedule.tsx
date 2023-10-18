import { useSWR } from '../../lib/fetcher';
import { useState, useEffect, useMemo } from 'react';

interface Stop {
    location_type: string;
}

export default function Caltrain() {
    const today  = Date.now()
    const { data: trips } = useSWR(`/api/v1/feeds/1/trips`);
    const { data: services } = useSWR(`/api/v1/feeds/1/services`);
    const { data: stops } = useSWR(`/api/v1/feeds/1/stops`);
    const [processedServices, setProcessedServices] = useState([]);
    const [activeServices, setActiveServices] = useState([]);
    const [activeTrips, setActiveTrips] = useState([]);


    // Record the to and from selection options, by stop Id.
    const [fromStop, setFromStop] = useState(-1);
    const [toStop, setToStop] = useState(-1);
    const [matchingTrips, setMatchingTrips] = useState([]);

    const stopsMap = useMemo(
        () => buildStopsParentMap(stops),
        [stops]
      );

    useEffect(() => {
        if (fromStop === -1 || toStop === -1) return;
        console.log(`from: ${fromStop} to: ${toStop}`);
        let matchingTrips = lookupTrip(fromStop, toStop, activeTrips, stopsMap);
        setMatchingTrips(matchingTrips);
    }, [fromStop, toStop]);

    useEffect(() => {
        if (services === undefined) return;
        
        let s = [];
        let as = [];
        services.forEach(service => {
            let sched = convertServiceScheduleToArray(service);
            let inService = isInService(service);
            let activeToday = sched[new Date(today).getDay()];
            if (activeToday && inService) as.push(service.id);
            s.push({sched, activeToday, inService, ...service})
        });
        setActiveServices(as);
        setProcessedServices(s);
        // Filter down the active trips.
        if (trips === undefined) return;
        let t = trips.filter(t => activeServices.includes(t.service));
        setActiveTrips(t);
    }, [services, trips])

    return (
    <div>
        <h1>Caltrain Schedule</h1>
        <div>Today is a: {convertDayToIntlStr(today)}</div>
        <fieldset>
            <h2>Trip Planner</h2>
            <label htmlFor="from">From:</label>
            <select id="from" onChange={e => setFromStop(parseInt(e.target.value))} >
                <option value="-1">select the beginning stop</option>
                {stops?.filter(stop => stop.location_type === "1").map((stop, idx) => {
                    return (
                    <option key={idx} value={stop.id}>
                        {stop.name}
                    </option>)
                })}
            </select>
            <label htmlFor="to">To:</label>
            <select id="to" onChange={e => setToStop(parseInt(e.target.value))}>
                <option value="-1">select the ending stop</option>
                {stops?.filter(stop => stop.location_type === "1").map((stop, idx) => {
                    return (
                    <option key={idx} value={stop.id}>
                        {stop.name}
                    </option>)
                })}
            </select>
        </fieldset>
        <div>
            {matchingTrips?.sort(dateComparator).map((t, idx) => {
                // okay these all match our trip, let's check out the times we get to the from -> to stops.
                let fromList = stopsMap[fromStop];
                let toList = stopsMap[toStop];

                let from = t.stops.find(t => fromList.includes(t.stop));
                let fromStopObj = stops.find(s => s.id === from.stop);
                let to = t.stops.find(t => toList.includes(t.stop));
                let toStopObj = stops.find(s => s.id === to.stop);

                return (
                <div key={idx}>
                    {t.short_name}: {t.headsign} {convertDirectionToStr(parseInt(t.direction))}
                    <div>
                        {formatTime(from.arrival_time).toLocaleTimeString('en-US')} -- {formatTime(to.arrival_time).toLocaleTimeString('en-US')}
                    </div>
                </div>);})}
        </div>

        <hr />
        <h2>Services</h2>
        <div>
            {processedServices?.map((s, idx) => { 
                return(
                <div key={idx}>
                    {s.service_id}({s.id}) - active? {s.activeToday && s.inService ? "yes": "no"}
                </div>
            )})}
        </div>
        <hr />
        <h2>Stops</h2>
        <div>
            {stops?.filter(stop => stop.location_type === "1").map((stop, idx) => {
                return (
                <div key={idx}>
                    {stop.name}
                </div>)
            })}
        </div>
        <hr />
        <h2>Trips</h2>
        <div>
            {trips?.sort(dateComparator).map((t, idx) => {
                if (!activeServices.includes(t.service)) return;
                return (<div key={idx}>
                    {t.short_name}: {t.headsign} {convertDirectionToStr(parseInt(t.direction))}
                    &nbsp;@&nbsp;
                    {t.stops[0].arrival_time}
                </div>);})}
        </div>
    </div>);
}

function buildStopsParentMap(stops: any[]|null) {
    if (!stops) return {};
    let m = {};

    for (let stop of stops) {
        let id = stop.id;
        if (stop.location_type === "1") {
            if (id in m) continue;
            m[id] = [];
            continue;
        }
        // else we are a child location.
        let parent = stop.parent_station;
        if (!(parent in m)) {
            m[parent] = [];
        }
        m[parent].push(id);
    }
    return m;
}

function lookupTrip(from: number, to: number, trips: any, stopsMap: any) {
    // Convert our single id's to the child stations
    let fromList = stopsMap[from];
    let toList = stopsMap[to];

    console.log(`from ${fromList}, to ${toList}`);

    // begin to filter trips, remove trips that don't contain any of the stops.
    let stopsToFind = [...fromList, ...toList];
    let t = [];
    for (let trip of trips) {
        let stops = trip.stops;
        let stopIds = stops.map(s => parseInt(s.stop));
        let intersection = stopIds.filter(x => stopsToFind.includes(x));
        if (intersection.length > 0) t.push(trip);
    }
    // Now check that the stops are in the correct order.
    console.log(t);
    let t2 = [];
    for (let trip of t) {
        let stops = trip.stops;
        let fromMatch = false;
        let toMatch = false;
        console.log(stops);
        for (let stop of stops) {
            let stop_id = stop.stop;
            if (fromList.includes(stop_id)) {
                fromMatch = true;
                console.log("match From")
            }
            if (toList.includes(stop_id)) {
                if (!fromMatch) {
                    console.log('Out of order!')
                    // out of order! EXIT.
                    break;
                }
                console.log('from & to match')
                toMatch = true;
            }
        }
        if (fromMatch && toMatch) t2.push(trip);
    }
    console.log(t2);
    return t2;
}

function isInService(service: any): boolean {
    let today = new Date();
    today.setHours(0,0,0,0);
    // Added by exception.
    let additions = service.dates.filter(s => s.exception_type === 1)
    for (let exception of additions) {
        console.log(exception);
        let d = new Date(exception.date);
        console.log(`${today.toUTCString()} - ${d.toUTCString()}`)
        if (d === today) {
            console.log('match');
            return true;
        }
    }

    // Removed by exception.
    let removal = service.dates.filter(s => s.exception_type === 2)
    for (let exception of removal) {
        console.log(exception);
        let d = new Date(exception.date);
        console.log(`${today.toUTCString()} - ${d.toUTCString()}`)
        if (d === today) {
            console.log('match (negative)');
            return false;
        }
    }
    // If we are in usual service
    let start = new Date(service.start_date);
    let end = new Date(service.end_date);

    if (today > start && today < end) {
        console.log("we are in normal service");
        return true;
    }

    return false;
}


function dateComparator(a: any, b: any): number {
    const timeRegex = /[\d]{2}/g;
    const aParts = a.stops[0].arrival_time.match(timeRegex);
    const bParts = b.stops[0].arrival_time.match(timeRegex);

    const aDate = new Date();
    const bDate = new Date();
    aDate.setHours(aParts[0], aParts[1], aParts[2]);
    bDate.setHours(bParts[0], bParts[1], bParts[2]);
    return aDate.getTime() - bDate.getTime();
}

function formatTime(time: string) {
    const timeRegex = /[\d]{2}/g;
    const parts = time.match(timeRegex);
    const d = new Date();
    d.setHours(parts[0], parts[1], parts[2]);
    return d;

}

function convertDayToIntlStr(date: number) {
    const options = { weekday: "long", timeZone: 'America/Los_Angeles' } as Intl.DateTimeFormatOptions;
    return new Intl.DateTimeFormat("en-US", options).format(date);
}

function convertServiceScheduleToArray(service: any) {
    // Sunday - Saturday : 0 - 6
    let sched = [false, false, false, false, false, false, false];
    sched[0] = service.sunday ?? false;
    sched[1] = service.monday ?? false;
    sched[2] = service.tuesday ?? false;
    sched[3] = service.wednesday ?? false;
    sched[4] = service.thursday ?? false;
    sched[5] = service.friday ?? false;
    sched[6] = service.saturday ?? false;
    return sched;
}

function convertDirectionToStr(direction: number): string {
    switch (direction) {
        case 0:
            return "Northbound"
        case 1:
            return "Southbound"
        default:
            return "Unknown Direction"
    }
}