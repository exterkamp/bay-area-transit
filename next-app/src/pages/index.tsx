import Head from 'next/head'

import { useSWR } from '../lib/fetcher';

export default function Home() {
  const { data: feed } = useSWR(`/api/v1/feeds/1`);
  const { data: agency } = useSWR(`/api/v1/feeds/1/agencies/1`);
  // const { data: routes } = useSWR(`/api/v1/feeds/1/agencies/1/routes`);


  return (
    <div>
      <Head>
        <title>Bay Area Transit</title>
        <link rel="icon" href="/favicon.ico" />
      </Head>

      <main>
        <h1>GTFS Feeds debug</h1>
        <div>
          {JSON.stringify(feed)}
          <br/>
          {JSON.stringify(agency)}
          {/* <br/> */}
          {/* {JSON.stringify(routes)} */}
        </div>
      </main>
    </div>
  )
}
