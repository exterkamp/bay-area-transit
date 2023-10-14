import Head from 'next/head'
import Map from '../components/map'
import { useState, useEffect } from 'react'
import { useSWR } from '../lib/fetcher';
// import { Marker } from 'react-leaflet/Marker'
// import { Popup } from 'react-leaflet/Popup'




export default function Caltrain() {
    const [center, setCenter] = useState([37.4334, -122.0815]);
    const [zoom, setZoom] = useState(9);
    const [markers, setMarkers] = useState([]);

    const { data: stops } = useSWR(`/api/v1/feeds/1/stops`);

    useEffect(() => {
        if (stops === undefined) return;
        // let points = stops.map(stop => stop.point.coordinates).map(coors => coors.reverse());
        // console.log(points);
        setMarkers(stops);
        // setMarkers()

        // setPersonnel(organization.personnel);
        // let config = organization.mapBoxConfig;
        // if (!!config) {
        //     setCenter([config.lat, config.lng]);
        //     setZoom(config.defaultZoom);
        // }
    }, [stops])

  return (
    <div>
      <Head>
        <title>Bay Area Transit</title>
        <link rel="icon" href="/favicon.ico" />
      </Head>

      <main>
        <h1>Caltrain</h1>
        <div>
            <Map center={center} zoom={zoom} markers={markers}>
                    {({ Marker, Popup }: any) => 
                    
                    // (
                    //     <>
                    //         <Marker position={center} />
                    //     </>
                        
                    // )

                    
                        markers.map((marker, idx) => 
                        {
                            console.log(marker);
                            let position = marker.point.coordinates.reverse();
                            return (
                                <Marker key={`marker-${idx}`} position={position}>
                                    <Popup>
                                        <span>{marker.name}</span>
                                    </Popup>
                                </Marker>)
                        }
                    )
                
                    
                    }
                {/* {markers.map((position, idx) => 
                    <Marker key={`marker-${idx}`} position={position}>
                    </Marker>
                )} */}
            </Map>
        </div>
      </main>
    </div>
  )
}
