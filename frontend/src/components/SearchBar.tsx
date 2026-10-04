import { useMemo } from "react";
import type { RouteSummary } from "../types";

interface Props {
  routes: RouteSummary[];
  search: string;
  onSearchChange: (value: string) => void;
  onSelectRoute: (routeId: string) => void;
}

export default function SearchBar({ routes, search, onSearchChange, onSelectRoute }: Props) {
  const results = useMemo(() => {
    if (!search.trim()) return [];
    const q = search.trim().toLowerCase();

    // Rank so an exact or prefix match on the route number (the common
    // case -- typing "2" for route 2) always beats routes that merely
    // contain the query as a substring (e.g. "102", "120", "28"), which
    // would otherwise crowd it out of a plain alphabetical top-8.
    function rank(r: RouteSummary): number {
      const id = r.route_id.toLowerCase();
      const shortName = r.short_name?.toLowerCase() ?? "";
      if (id === q || shortName === q) return 0;
      if (id.startsWith(q) || shortName.startsWith(q)) return 1;
      if (id.includes(q) || shortName.includes(q)) return 2;
      return 3; // only the long name matched
    }

    return routes
      .filter(
        (r) =>
          r.route_id.toLowerCase().includes(q) ||
          r.short_name?.toLowerCase().includes(q) ||
          r.long_name?.toLowerCase().includes(q)
      )
      .sort((a, b) => rank(a) - rank(b))
      .slice(0, 8);
  }, [routes, search]);

  return (
    <div className="search-bar">
      <div className="search-input-wrap">
        <svg className="search-icon" viewBox="0 0 24 24" width="18" height="18" fill="none">
          <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="2" />
          <path d="M21 21l-4.3-4.3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
        <input
          type="text"
          placeholder="Search a bus route (e.g. 720)"
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          autoComplete="off"
        />
      </div>
      {results.length > 0 && (
        <ul className="search-results">
          {results.map((r) => (
            <li key={r.route_id}>
              <button type="button" onClick={() => onSelectRoute(r.route_id)}>
                <span className="route-chip">{r.short_name ?? r.route_id}</span>
                <span className="route-name">{r.long_name ?? "Metro Bus"}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
