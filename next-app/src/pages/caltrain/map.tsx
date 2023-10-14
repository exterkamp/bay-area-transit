import Head from 'next/head'
import Map from '../../components/map'
import { useState, useEffect } from 'react'
import { useSWR } from '../../lib/fetcher';

export default function Caltrain() {
    const [center, setCenter] = useState([37.4334, -122.0815]);
    const [zoom, setZoom] = useState(9);
    const [markers, setMarkers] = useState([]);

    const { data: stops } = useSWR(`/api/v1/feeds/1/stops`);

    useEffect(() => {
        if (stops === undefined) return;
        setMarkers(stops);
    }, [stops])

  return (
    <div>
      <Head>
        <title>Bay Area Transit</title>
        <link rel="icon" href="/favicon.ico" />
      </Head>

      <main>
        <div>
            <Map center={center} zoom={zoom} markers={markers}>
                    {({ Marker, Popup }: any) => 
                        markers.map((marker, idx) => {
                            console.log(marker);
                            if (marker.location_type !== "1") return;
                            let position = marker.point.coordinates.reverse();
                            return (
                                <Marker key={`marker-${idx}`} position={position}>
                                    <Popup>
                                        <span>{marker.name}</span>
                                    </Popup>
                                </Marker>)
                        })}
            </Map>
        </div>
      </main>
    </div>
  )
}
