import Head from 'next/head'
import useSWR from 'swr'
import React, { useState, useEffect } from 'react';

import styles from '../styles/index.module.scss'
import { Operator, Line, Stop, StopType } from '../types'


export default function Home() {
  const [selectedOperator, setSelectedOperator] = useState("");

  const { data: operators, isLoading: isLoadingOperators } = useSWR('/api/operators',
    url => fetch(url).then(r => r.json() as Promise<Operator[]>))

  function setOperator(event) {
    let val = event.target.value;
    setSelectedOperator(val);
  }

  return (
    <>
      <Head>
        <title>Bay Area Transit</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <link rel="icon" href="/favicon.ico" />
      </Head>
      <main className={styles.main}>
        <div className={styles.maxWidthContainer}>
          <h1>Bay Area Transit</h1>
          <h2>Select Transit operator</h2>
          {!isLoadingOperators
            ? <section>
              <select onChange={setOperator} >
                <option></option>
                {operators?.map(element => {
                  return <option key={element.id} value={element.id} >{element.name}</option>;
                })}
              </select>
            </section>
            : <></>
          }
          {selectedOperator !== "" ? <StopPicker operator={selectedOperator} /> : <></>}
        </div>
      </main>
    </>
  )
}

function StopPicker(props: { operator: string }) {
  let operator = props.operator;
  const { data: stops, isLoading: isLoadingStops } = useSWR(`/api/operators/${operator}/stops`,
    url => fetch(url).then(r => r.json() as Promise<Stop[]>));

  const { data: lines, isLoading: isLoadingLines } = useSWR(`/api/operators/${operator}/lines`,
  url => fetch(url).then(r => r.json() as Promise<Line[]>));

  // once we have a start & stop id.
  // get the current day, or whichever day we are planning.
  // get the patterns (cheap) for those lines.
  // look through routes to find id = start id.
    //  save those routes.
    //  filter out routes where idx[start] > idx[end] (this means we're going the wrong way)
  // get all the lines that cover that day.
    // get our timetables (expensive) for the remaining lines!
  // for valid routes (perhaps this is just one at this point)
  //  fetch subroute starting from [start] -> [finish]
  //  attach time's to the stops

  return (
    <div>
      <span>Pickup</span>
      {!isLoadingStops
        ? <select>
          {stops?.filter(element => element.extensions.type === StopType.Station).map(element => {
            return <option key={element.id} value={element.id}>{element.name}</option>
          })}
        </select>
        : <></>
      }
      <br/>
      <span>Dropoff</span>
      {!isLoadingStops
        ? <select>
          {stops?.filter(element => element.extensions.type === StopType.Station).map(element => {
            return <option key={element.id} value={element.id}>{element.name}</option>
          })}
        </select>
        : <></>
      }
      <br/>
      {!isLoadingLines ? <span>{JSON.stringify(lines)}</span>: <></>}
    </div>
  );
}