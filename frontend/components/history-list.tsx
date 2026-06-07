"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { useRequireAuth } from "@/lib/use-require-auth";
import type { Trip } from "@/lib/types";

export function HistoryList() {
  const router = useRouter();
  const authed = useRequireAuth();
  const [trips, setTrips] = useState<Trip[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!authed) return;
    api
      .listTrips()
      .then(setTrips)
      .catch((loadError) => setError(loadError instanceof Error ? loadError.message : "Falha ao carregar viagens."))
      .finally(() => setLoading(false));
  }, [authed]);

  return (
    <section className="panel" style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      <header
        className="workspace-header"
        style={{ display: "flex", alignItems: "center", gap: "1rem", flexWrap: "wrap" }}
      >
        <h1 style={{ margin: 0, marginRight: "auto" }}>Minhas Viagens</h1>
        <Link
          href="/profile"
          className="button-secondary"
          style={{ padding: "0.5rem 1rem", borderRadius: "12px", fontSize: "0.9rem" }}
        >
          Minha conta
        </Link>
        <Link
          href="/trips/new"
          className="button-primary"
          style={{ padding: "0.5rem 1rem", borderRadius: "12px", fontSize: "0.9rem" }}
        >
          + Nova viagem
        </Link>
      </header>

      {error ? <div className="notice-banner notice-banner--error">{error}</div> : null}

      {loading && !error ? (
        <p className="lede">Carregando viagens...</p>
      ) : trips.length === 0 ? (
        <div
          className="option-tile"
          style={{ textAlign: "center", padding: "2.5rem 1.5rem", display: "flex", flexDirection: "column", gap: "1rem", alignItems: "center" }}
        >
          <strong style={{ fontSize: "1.1rem" }}>Você ainda não tem viagens</strong>
          <p className="lede" style={{ margin: 0 }}>
            Crie seu primeiro roteiro e ele aparecerá aqui.
          </p>
          <Link href="/trips/new" className="button-primary" style={{ marginTop: "0.25rem" }}>
            Criar primeira viagem
          </Link>
        </div>
      ) : (
        <div className="history-grid" style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
          {trips.map((trip) => (
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
          ))}
        </div>
      )}
    </section>
  );
}
