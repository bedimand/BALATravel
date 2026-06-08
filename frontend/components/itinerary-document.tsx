"use client";

import { useMemo } from "react";

// A single normalized stop on the trip — both the authenticated export view
// (built from map markers) and the public share page (built from itinerary
// items) map their own data into this shape so they can share one renderer.
export type DocStop = {
  key: string;
  date: string;
  title: string;
  kind: string;
  startTime?: string | null;
  note?: string | null;
  imageUrl?: string | null;
  rating?: number | null;
  address?: string | null;
  website?: string | null;
  lat?: number | null;
  lng?: number | null;
  googlePlaceId?: string | null;
};

const KIND_ICONS: Record<string, string> = {
  restaurant: "🍽",
  museum: "🏛",
  attraction: "🎯",
  park: "🌳",
  nightlife: "🎭",
  shopping: "🛍",
  hotel: "🏨",
  accommodation: "🏠",
  default: "📍",
};

// "09:00:00" / "09:00" → "09:00"; leaves anything unexpected untouched.
function formatTime(value?: string | null): string {
  if (!value) return "";
  const match = value.match(/^(\d{1,2}):(\d{2})/);
  return match ? `${match[1].padStart(2, "0")}:${match[2]}` : value;
}

// Build a Google Maps link that opens the actual place card. When we have the
// Google Place ID, `query_place_id` resolves to the real listing (a bare
// `query=lat,lng` only drops an anonymous pin at the coordinates). The `query`
// param is still required by the Maps URL API and acts as the human-readable
// label / fallback, so we always send the place name scoped to the destination.
function mapsHref(stop: DocStop, destination: string): string {
  const query = encodeURIComponent(`${stop.title} ${destination}`.trim());
  const base = `https://www.google.com/maps/search/?api=1&query=${query}`;
  if (stop.googlePlaceId) {
    return `${base}&query_place_id=${stop.googlePlaceId}`;
  }
  return base;
}

type Props = {
  destination: string;
  startDate: string;
  endDate: string;
  stops: DocStop[];
  /** Renders external website/maps links per stop. */
  showLinks?: boolean;
};

export function ItineraryDocument({ destination, startDate, endDate, stops, showLinks = true }: Props) {
  // Group by date, each day sorted by start time, days in chronological order.
  const days = useMemo(() => {
    const dates = Array.from(new Set(stops.map((s) => s.date).filter(Boolean))).sort();
    return dates.map((date, idx) => ({
      date,
      dayNumber: idx + 1,
      items: stops
        .filter((s) => s.date === date)
        .sort((a, b) => (a.startTime || "").localeCompare(b.startTime || "")),
    }));
  }, [stops]);

  return (
    <article className="export-doc">
      <header className="export-doc__head">
        <p className="export-doc__brand">BALATravel</p>
        <h1>{destination}</h1>
        <p className="export-doc__dates">
          {startDate} — {endDate}
        </p>
      </header>

      {days.length === 0 ? (
        <p className="export-doc__empty">Este roteiro ainda não tem atividades planejadas.</p>
      ) : (
        days.map((day) => (
          <section key={day.date} className="export-day">
            <div className="export-day__head">
              <span className="export-day__num">Dia {day.dayNumber}</span>
              <span className="export-day__date">{day.date}</span>
              <span className="export-day__count">
                {day.items.length} {day.items.length === 1 ? "parada" : "paradas"}
              </span>
            </div>

            <ol className="export-day__list">
              {day.items.map((stop) => {
                const icon = KIND_ICONS[stop.kind] ?? KIND_ICONS.default;
                const time = formatTime(stop.startTime);
                return (
                  <li key={stop.key} className="export-stop">
                    <div className="export-stop__time">{time || "—"}</div>
                    <div className="export-stop__thumb" aria-hidden>
                      {stop.imageUrl ? (
                        // Google CDN photos 403 without a stripped referrer; eager
                        // load so they're decoded before a print-to-PDF fires.
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={stop.imageUrl}
                          alt=""
                          loading="eager"
                          referrerPolicy="no-referrer"
                          onError={(e) => {
                            (e.currentTarget as HTMLImageElement).style.display = "none";
                          }}
                        />
                      ) : (
                        <span>{icon}</span>
                      )}
                    </div>
                    <div className="export-stop__body">
                      <div className="export-stop__title-row">
                        <h3>{stop.title}</h3>
                        {stop.rating != null && (
                          <span className="export-stop__rating">★ {stop.rating}</span>
                        )}
                      </div>
                      <p className="export-stop__kind">{stop.kind}</p>
                      {stop.address && <p className="export-stop__addr">📍 {stop.address}</p>}
                      {stop.note && <p className="export-stop__note">{stop.note}</p>}
                      {showLinks && (
                        <div className="export-stop__links">
                          {stop.website && (
                            <a href={stop.website} target="_blank" rel="noreferrer">
                              🌐 Website
                            </a>
                          )}
                          <a href={mapsHref(stop, destination)} target="_blank" rel="noreferrer">
                            🗺 Abrir no Google Maps
                          </a>
                        </div>
                      )}
                    </div>
                  </li>
                );
              })}
            </ol>
          </section>
        ))
      )}
    </article>
  );
}
