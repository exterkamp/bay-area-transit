// Based off: https://github.com/colbyfayock/next-leaflet-starter

import dynamic from 'next/dynamic';

const DynamicMap = dynamic(() => import('./map'), {
  ssr: false,
});

// This is the no SSR dynamic wrapper to the map component.
// This is needed because react-leaflet relies on window, and cannot be rendered
// server side, so it must be disabled.
export default DynamicMap;