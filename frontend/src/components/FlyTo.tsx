import { useEffect } from "react";
import { useMap } from "react-leaflet";

export default function FlyTo({ position, zoom = 15 }: { position: [number, number] | null; zoom?: number }) {
  const map = useMap();

  useEffect(() => {
    if (position) {
      map.flyTo(position, zoom, { duration: 0.6 });
    }
  }, [position, zoom, map]);

  return null;
}
