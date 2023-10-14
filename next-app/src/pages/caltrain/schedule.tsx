import { useSWR } from '../../lib/fetcher';
import { useState, useEffect } from 'react'


export default function Caltrain() {
    const today  = Date.now()
    const { data: trips } = useSWR(`/api/v1/feeds/1/trips`);
    const { data: services } = useSWR(`/api/v1/feeds/1/services`);
    const [processedServices, setProcessedServices] = useState([]);
    const [activeServices, setActiveServices] = useState([]);

    useEffect(() => {
        if (services === undefined) return;
        
        let s = [];
        let as = [];
        services.forEach(service => {
            let sched = convertServiceScheduleToArray(service);
            let activeToday = sched[new Date(today).getDay()];
            if (activeToday) as.push(service.id);
            s.push({sched, activeToday, ...service})
        });
        setActiveServices(as);
        setProcessedServices(s)
    }, [services])

    return (
    <div>
        <h1>Caltrain Schedule</h1>
        <div>Today is a: {convertDayToIntlStr(today)}</div>
        <hr />
        <h2>Services</h2>
        <div>
            {processedServices?.map((s, idx) => { 
                return(
                <div key={idx}>
                    {s.service_id}({s.id}) - active today? {s.activeToday ? "yes": "no"}
                </div>
            )})}
        </div>
        <hr />
        <h2>Trips</h2>
        <div>
            {trips?.map((t, idx) => {
                if (!activeServices.includes(t.service)) return;
                return (<div key={idx}>
                    {t.short_name}: {t.headsign} {convertDirectionToStr(parseInt(t.direction))}
                </div>);})}
        </div>
    </div>);
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
            return "Southbound"
        case 1:
            return "Northbound"
        default:
            return "Unknown Direction"
    }
}