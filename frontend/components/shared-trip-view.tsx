"use client";

import { useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import type { PublicTrip } from "@/lib/types";
import { ItineraryDocument, type DocStop } from "./itinerary-document";
import { exportDocStyles } from "./export-styles";

type Props = { token: string };

// Public, no-auth read-only view of a shared itinerary. The public API only
// returns itinerary items (not the enriched Place rows), so there are no
// photos/ratings/websites here — but lat/lng survive, so the Google Maps link
// per stop still resolves.
export function SharedTripView({ token }: Props) {
  const [trip, setTrip] = useState<PublicTrip | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getPublicTrip(token)
      .then(setTrip)
      .catch((e) => setError(e instanceof Error ? e.message : "Roteiro não encontrado."))
      .finally(() => setLoading(false));
  }, [token]);

  const stops = useMemo<DocStop[]>(() => {
    const items = trip?.itinerary?.items ?? [];
    return items.map((item) => ({
      key: String(item.id),
      date: item.date,
      title: item.title,
      kind: item.item_type,
      startTime: item.start_time,
      note: item.curator_reasoning || item.notes,
      lat: item.lat,
      lng: item.lng,
    }));
  }, [trip]);

  if (loading) {
    return (
      <main className="export-page">
        <p className="export-loading">Carregando roteiro…</p>
        <style dangerouslySetInnerHTML={{ __html: exportDocStyles }} />
      </main>
    );
  }

  if (error || !trip) {
    return (
      <main className="export-page">
        <p className="export-loading">{error ?? "Roteiro não encontrado ou link expirado."}</p>
        <style dangerouslySetInnerHTML={{ __html: exportDocStyles }} />
      </main>
    );
  }

  return (
    <main className="export-page">
      <div className="export-toolbar">
        <span className="export-back" style={{ color: "#6b7280", cursor: "default", display: "flex", alignItems: "center", gap: "0.5rem" }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/icone.png" alt="" style={{ width: "1.4rem", height: "1.4rem", objectFit: "contain" }} />
          Roteiro compartilhado · BALATravel
        </span>
        <button className="export-btn export-btn--ghost" onClick={() => window.print()}>
          🖨 Imprimir / Salvar PDF
        </button>
      </div>

      <ItineraryDocument
        destination={trip.destination}
        startDate={trip.start_date}
        endDate={trip.end_date}
        stops={stops}
        showLinks
      />

      <style dangerouslySetInnerHTML={{ __html: exportDocStyles }} />
    </main>
  );
}
