// @ts-nocheck

import { MapContainer, TileLayer } from 'react-leaflet'
import React, { useEffect, useMemo, useState, useCallback } from "react";
// import styles from '../../styles/components/Map.module.css';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import * as ReactLeaflet from 'react-leaflet';
import iconRetinaUrl from 'leaflet/dist/images/marker-icon-2x.png';
import iconUrl from 'leaflet/dist/images/marker-icon.png';
import shadowUrl from 'leaflet/dist/images/marker-shadow.png';


export default function MapWithMarkers({ children, className, ...rest }: any /* { center, zoom, markers, updateCenterCallback }: any */) {
    const [map, setMap] = useState(null);
    const displayMap = useMemo(
        () => (
            <MapContainer {...rest}
                id="map"
                scrollWheelZoom={false}
                style={{ height: '400px', }}
                ref={setMap} >
                <TileLayer
                    attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                    url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                />
                {children(ReactLeaflet)}
            </MapContainer>
        ),
        [children, rest]
    )

    // Setup the icon.
    useEffect(() => {
        (async function init() {
            delete L.Icon.Default.prototype._getIconUrl;

            L.Icon.Default.mergeOptions({
                iconRetinaUrl: iconRetinaUrl.src,
                iconUrl: iconUrl.src,
                shadowUrl: shadowUrl.src,
            });
        })();
    }, []);

    // if center/zoom changes, set our pos.
    useEffect(() => {
        if (map === null) return;
        map.setView(rest.center, rest.zoom)
    }, [map, rest.center, rest.zoom]);

    return (
        <div>
            {map ? <DisplayPosition map={map} center={rest.center} initialZoom={rest.zoom} updateCenterCallback={rest.updateCenterCallback} /> : null}
            {displayMap}
        </div>
    );
}

function DisplayPosition({ map, center, initialZoom, updateCenterCallback }: any) {
    const [position, setPosition] = useState(() => map.getCenter());
    const [zoom, setZoom] = useState(() => map.getZoom());

    const onClick = useCallback(() => {
        map.setView(center, initialZoom)
    }, [map, initialZoom, center])

    const commitNewCenter = useCallback(() => {
        updateCenterCallback(position, zoom);
    }, [position, zoom, updateCenterCallback])

    const onMove = useCallback(() => {
        setPosition(map.getCenter())
    }, [map])

    const onZoom = useCallback(() => {
        setZoom(map.getZoom());
    }, [map]);

    useEffect(() => {
        map.on('move', onMove)
        return () => {
            map.off('move', onMove)
        }
    }, [map, onMove])

    useEffect(() => {
        map.on('zoom', onZoom)
        return () => {
            map.off('zoom', onZoom)
        }
    }, [map, onZoom])

    return (
        <div>
            <div>
                latitude: {position.lat.toFixed(4)}, longitude: {position.lng.toFixed(4)}{' '} (zoom: {zoom})
            </div>
            <button onClick={onClick}>reset map</button>
            {/* TODO: make this set the parent to the new center for the OP. */}
            {updateCenterCallback ? <button onClick={commitNewCenter}>new center</button> : null}
        </div>
    )
}