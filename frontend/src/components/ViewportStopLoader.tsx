import { useEffect, useRef } from "react";
import { useMap, useMapEvents } from "react-leaflet";
import { getNearbyStops } from "../api";
import type { NearbyStop } from "../types";

interface Props {
  onStopsChange: (stops: NearbyStop[]) => void;
  onError: (message: string) => void;
  onLoadingChange: (loading: boolean) => void;
}

/** Loads stops around wherever the map currently is, so panning the city
 *  reveals stops there instead of being stuck on the initial center.
 *  Retries on transient failure (cold start, etc.) are handled centrally
 *  in api.ts -- this just tracks loading state for the UI. */
export default function ViewportStopLoader({ onStopsChange, onError, onLoadingChange }: Props) {
  const map = useMap();
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  function load() {
    const center = map.getCenter();
    onLoadingChange(true);
    getNearbyStops(center.lat, center.lng, 200)
      .then(onStopsChange)
      .catch((err) => onError(err.message))
      .finally(() => onLoadingChange(false));
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
