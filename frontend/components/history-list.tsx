"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { Trip } from "@/lib/types";

export function HistoryList() {
  const router = useRouter();
  const [trips, setTrips] = useState<Trip[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listTrips()
      .then(setTrips)
      .catch((loadError) => setError(loadError instanceof Error ? loadError.message : "Falha ao carregar viagens."));
  }, []);

  return (
    <section className="panel" style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      <header className="workspace-header" style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
        <button 
          onClick={() => router.back()} 
          className="button-secondary" 
          style={{ padding: "0.5rem 1rem", borderRadius: "12px", fontSize: "0.9rem" }}
        >
          ← Voltar
        </button>
        <h1 style={{ margin: 0 }}>Histórico de Viagens</h1>
      </header>
      
      {error ? <div className="notice-banner notice-banner--error">{error}</div> : null}
      
      <div className="history-grid" style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
        {trips.length === 0 && !error ? (
          <p className="lede">Carregando histórico...</p>
        ) : (
          trips.map((trip) => (
            <Link href={`/trips/${trip.id}`} key={trip.id} className="history-card option-tile option-tile--featured">
              <div>
                <strong>{trip.destination}</strong>
                <p className="lede" style={{ fontSize: "0.9rem" }}>
                  {trip.start_date} até {trip.end_date}
                </p>
              </div>
              <div className="option-tile__meta">
                <span className={`stage-pill ${trip.status === "draft" ? "stage-pill--waiting_user" : "stage-pill--ready"}`}>
                  {trip.status === "draft" ? "Rascunho" : trip.status === "planned" ? "Planejado" : trip.status}
                </span>
              </div>
            </Link>
          ))
        )}
      </div>
    </section>
  );
}
