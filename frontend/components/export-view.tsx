"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import { useRequireAuth } from "@/lib/use-require-auth";
import type { WorkspaceResponse } from "@/lib/types";
import { ItineraryDocument, type DocStop } from "./itinerary-document";
import { exportDocStyles } from "./export-styles";

type Props = { tripId: string };

export function ExportView({ tripId }: Props) {
  useRequireAuth();
  const [workspace, setWorkspace] = useState<WorkspaceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [shareBusy, setShareBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getWorkspace(tripId)
      .then(setWorkspace)
      .catch((e) => setError(e instanceof Error ? e.message : "Falha ao carregar roteiro."))
      .finally(() => setLoading(false));
  }, [tripId]);

  // Map markers → normalized stops (skip the accommodation pin; it has no date).
  const stops = useMemo<DocStop[]>(() => {
    if (!workspace) return [];
    return workspace.map.markers
      .filter((m) => m.kind !== "accommodation" && m.date)
      .map((m) => ({
        key: m.id,
        date: m.date as string,
        title: m.title,
        kind: m.kind,
        startTime: m.start_time,
        note: m.curator_reasoning || m.editorial_note || m.summary,
        imageUrl: m.image_url,
        rating: m.rating,
        address: m.address_full,
        website: m.website,
        lat: m.lat,
        lng: m.lng,
        googlePlaceId: m.google_place_id,
      }));
  }, [workspace]);

  const generateShareLink = useCallback(async () => {
    setShareBusy(true);
    setCopied(false);
    try {
      const link = await api.createShareLink(tripId);
      // link.public_url is the API path (/api/share/{token}); the human-facing
      // page lives at /share/{token} on this same frontend origin.
      const origin = typeof window !== "undefined" ? window.location.origin : "";
      setShareUrl(`${origin}/share/${link.token}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Não foi possível gerar o link.");
    } finally {
      setShareBusy(false);
    }
  }, [tripId]);

  const copyShareLink = useCallback(async () => {
    if (!shareUrl) return;
    try {
      await navigator.clipboard.writeText(shareUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      setError("Não foi possível copiar. Copie manualmente o link acima.");
    }
  }, [shareUrl]);

  if (loading) {
    return (
      <main className="export-page">
        <p className="export-loading">Carregando roteiro…</p>
        <style dangerouslySetInnerHTML={{ __html: exportDocStyles }} />
      </main>
    );
  }

  if (error && !workspace) {
    return (
      <main className="export-page">
        <p className="export-loading">{error}</p>
        <Link className="export-back" href={`/trips/${tripId}`}>
          ← Voltar ao roteiro
        </Link>
        <style dangerouslySetInnerHTML={{ __html: exportDocStyles }} />
      </main>
    );
  }

  const trip = workspace!.trip;

  return (
    <main className="export-page">
      {/* Toolbar — hidden when printing */}
      <div className="export-toolbar">
        <Link className="export-back" href={`/trips/${tripId}`}>
          ← Voltar
        </Link>
        <div className="export-toolbar__actions">
          <button className="export-btn export-btn--ghost" onClick={() => window.print()}>
            🖨 Imprimir / Salvar PDF
          </button>
          {shareUrl ? (
            <button className="export-btn export-btn--primary" onClick={copyShareLink}>
              {copied ? "✓ Copiado!" : "🔗 Copiar link público"}
            </button>
          ) : (
            <button
              className="export-btn export-btn--primary"
              onClick={generateShareLink}
              disabled={shareBusy}
            >
              {shareBusy ? "Gerando…" : "🔗 Gerar link público"}
            </button>
          )}
        </div>
      </div>

      {shareUrl && (
        <div className="export-sharebar">
          <span className="export-sharebar__label">Link público (válido por 14 dias):</span>
          <a className="export-sharebar__url" href={shareUrl} target="_blank" rel="noreferrer">
            {shareUrl}
          </a>
        </div>
      )}

      {error && <p className="export-inline-error">{error}</p>}

      {trip.accommodation_name && (
        <p className="export-accom">🏠 Hospedagem: <strong>{trip.accommodation_name}</strong></p>
      )}

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
