"use client";

import { useMemo } from "react";
import type { MapResponse } from "@/lib/types";

// Mirror of map-panel.tsx DAY_COLORS so a day's timeline accent matches its map pins.
const DAY_COLORS = [
  "#00ff41",
  "#f1c40f",
  "#e74c3c",
  "#9b59b6",
  "#3498db",
  "#e67e22",
  "#1abc9c",
];

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

type Marker = MapResponse["markers"][number];

type Props = {
  markers: Marker[];
  dates: string[];
  activeDay: string | null;
  selectedPlaceId: string | null;
  onPlaceClick: (id: string) => void;
  highlightIds?: Set<string>;
  compact?: boolean;
};

export function TripTimeline({
  markers,
  dates,
  activeDay,
  selectedPlaceId,
  onPlaceClick,
  highlightIds,
  compact = false,
}: Props) {
  // Color per date, indexed by the sorted date order (matches map-panel).
  const dateColors = useMemo(() => {
    const sorted = [...dates].sort();
    const colors: Record<string, string> = {};
    sorted.forEach((d, i) => {
      colors[d] = DAY_COLORS[(i + 1) % DAY_COLORS.length];
    });
    return colors;
  }, [dates]);

  // Group visible (non-accommodation) markers by date, each day sorted by start_time.
  const days = useMemo(() => {
    const sortedDates = [...dates].sort();
    return sortedDates
      .filter((d) => !activeDay || activeDay === "all" || d === activeDay)
      .map((date, idx) => {
        const items = markers
          .filter((m) => m.kind !== "accommodation" && m.date === date)
          .sort((a, b) => (a.start_time || "").localeCompare(b.start_time || ""));
        return { date, dayNumber: idx + 1, items, color: dateColors[date] || DAY_COLORS[0] };
      });
  }, [markers, dates, activeDay, dateColors]);

  if (days.length === 0) {
    return (
      <div style={{ textAlign: "center", opacity: 0.35, marginTop: "3rem", fontSize: "0.85rem", padding: "0 1rem" }}>
        <p style={{ fontSize: "2rem", marginBottom: "0.5rem" }}>🗓</p>
        Os dias aparecem aqui conforme o agente monta o roteiro.
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: compact ? "1.25rem" : "1.5rem", padding: compact ? "0.75rem" : "0.5rem" }}>
      {days.map((day) => (
        <div key={day.date}>
          {/* Day header */}
          <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", marginBottom: "0.65rem", paddingLeft: "0.25rem" }}>
            <span style={{
              width: "10px", height: "10px", borderRadius: "50%",
              background: day.color, boxShadow: `0 0 10px ${day.color}66`, flexShrink: 0,
            }} />
            <strong style={{ fontSize: "0.82rem", letterSpacing: "0.3px" }}>Dia {day.dayNumber}</strong>
            <span style={{ fontSize: "0.68rem", opacity: 0.4, fontWeight: 600 }}>{day.date}</span>
            <span style={{ marginLeft: "auto", fontSize: "0.65rem", opacity: 0.4 }}>
              {day.items.length} {day.items.length === 1 ? "parada" : "paradas"}
            </span>
          </div>

          {day.items.length === 0 ? (
            <div style={{
              marginLeft: "0.75rem", padding: "0.6rem 0.85rem", borderRadius: "0.75rem",
              border: "1px dashed rgba(255,255,255,0.12)", fontSize: "0.72rem", opacity: 0.4,
            }}>
              Planejando…
            </div>
          ) : (
            // Timeline rail: vertical line + time-blocks
            <div style={{ position: "relative", marginLeft: "0.45rem", paddingLeft: "0.95rem", borderLeft: `2px solid ${day.color}33` }}>
              {day.items.map((marker) => {
                const isSelected = selectedPlaceId === marker.id;
                const isNew = highlightIds?.has(marker.id) ?? false;
                const icon = KIND_ICONS[marker.kind] ?? KIND_ICONS.default;
                return (
                  <div
                    key={marker.id}
                    onClick={() => onPlaceClick(marker.id)}
                    className={isNew ? "timeline-item timeline-item--new" : "timeline-item"}
                    style={{
                      position: "relative", marginBottom: "0.55rem", padding: "0.6rem 0.8rem",
                      borderRadius: "0.85rem", cursor: "pointer",
                      background: isSelected ? "rgba(0,229,255,0.1)" : "rgba(255,255,255,0.03)",
                      border: `1px solid ${isSelected ? "rgba(0,229,255,0.45)" : "rgba(255,255,255,0.05)"}`,
                      transition: "background 0.25s, border-color 0.25s, transform 0.25s",
                    }}
                  >
                    {/* node dot on the rail */}
                    <span style={{
                      position: "absolute", left: "-1.45rem", top: "0.85rem",
                      width: "9px", height: "9px", borderRadius: "50%",
                      background: isSelected ? "#00e5ff" : day.color,
                      border: "2px solid #0a0f1e", boxSizing: "content-box",
                    }} />
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                      {marker.start_time && (
                        <span style={{
                          fontSize: "0.68rem", fontWeight: 700, color: isSelected ? "#00e5ff" : "rgba(255,255,255,0.75)",
                          fontVariantNumeric: "tabular-nums", flexShrink: 0,
                        }}>{marker.start_time}</span>
                      )}
                      <span style={{ fontSize: "0.9rem", flexShrink: 0 }}>{icon}</span>
                      <span style={{
                        fontSize: "0.8rem", fontWeight: 500, color: isSelected ? "#00e5ff" : "white",
                        whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
                      }}>{marker.title}</span>
                      {isNew && (
                        <span style={{
                          marginLeft: "auto", fontSize: "0.6rem", fontWeight: 700, color: "#00e5ff",
                          background: "rgba(0,229,255,0.15)", padding: "1px 6px", borderRadius: "0.5rem", flexShrink: 0,
                        }}>novo</span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      ))}

      <style dangerouslySetInnerHTML={{ __html: `
        .timeline-item:hover { background: rgba(255,255,255,0.07) !important; transform: translateX(2px); }
        @keyframes timelinePop {
          0% { opacity: 0; transform: translateY(8px) scale(0.97); }
          60% { opacity: 1; transform: translateY(0) scale(1.02); }
          100% { opacity: 1; transform: translateY(0) scale(1); }
        }
        .timeline-item--new { animation: timelinePop 0.5s cubic-bezier(0.34, 1.56, 0.64, 1) both; }
      `}} />
    </div>
  );
}
