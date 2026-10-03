import { useEffect, useRef } from "react";
import { useMap, useMapEvents } from "react-leaflet";
import { getNearbyStops } from "../api";
import type { NearbyStop } from "../types";

interface Props {
  onStopsChange: (stops: NearbyStop[]) => void;
  onError: (message: string) => void;
}

/** Loads stops around wherever the map currently is, so panning the city
 *  reveals stops there instead of being stuck on the initial center. */
export default function ViewportStopLoader({ onStopsChange, onError }: Props) {
  const map = useMap();
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  function load() {
    const center = map.getCenter();
    getNearbyStops(center.lat, center.lng, 200)
      .then(onStopsChange)
      .catch((err) => onError(err.message));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useMapEvents({
    moveend: () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(load, 300);
    },
  });

  return null;
}
