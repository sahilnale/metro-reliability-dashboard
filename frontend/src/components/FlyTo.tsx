import { useEffect } from "react";
import { useMap } from "react-leaflet";

export default function FlyTo({ position }: { position: [number, number] | null }) {
  const map = useMap();

  useEffect(() => {
    // Pan to the stop without changing zoom -- forcing a fixed zoom level
    // here used to yank the view out from under anyone who'd already
    // zoomed in (or out) themselves.
    if (position) {
      map.panTo(position, { animate: true, duration: 0.6 });
    }
  }, [position, map]);

  return null;
}
