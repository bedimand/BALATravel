"use client";

import { useEffect, useState, useMemo } from "react";
import { api } from "@/lib/api";
import type { WorkspaceResponse } from "@/lib/types";
import { AgentThinking } from "./agent-thinking";
import { MapPanel } from "./map-panel";

type Props = {
  tripId: string;
};

export function TripPlanner({ tripId }: Props) {
  const [workspace, setWorkspace] = useState<WorkspaceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeDay, setActiveDay] = useState<string | null>("all");
  const [selectedPlaceId, setSelectedPlaceId] = useState<string | null>(null);
  const [composerText, setComposerText] = useState("");
  const [busyMessage, setBusyMessage] = useState(false);

  async function loadWorkspace() {
    try {
      const w = await api.getWorkspace(tripId);
      setWorkspace(w);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadWorkspace();
  }, [tripId]);

  const isAgentThinking = workspace?.workflow.stage_status === "running"
    || workspace?.workflow_runs?.some(r => r.status === "running");

  const dates = useMemo(() => {
    if (!workspace) return [];
    return Array.from(new Set(workspace.map.markers.map(m => m.date).filter(Boolean))) as string[];
  }, [workspace]);

  const selectedMarker = useMemo(() => workspace?.map.markers.find(m => m.id === selectedPlaceId), [workspace, selectedPlaceId]);

  async function handleChatSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!composerText.trim() || busyMessage) return;
    setBusyMessage(true);
    try {
      await api.sendWorkflowMessage(tripId, { message: composerText });
      setComposerText("");
      // Need to show AgentThinking again
      await loadWorkspace();
    } catch (e) {
      console.error(e);
    } finally {
      setBusyMessage(false);
    }
  }

  if (loading && !workspace) {
    return <div style={{ background: "#111", height: "100vh", color: "white", display: "grid", placeItems: "center" }}>Carregando Workspace...</div>;
  }

  if (!workspace) return <div>Falha ao carregar.</div>;

  return (
    <main className="workspace-app" style={{ 
      position: "relative", 
      height: "100dvh", 
      overflow: "hidden", 
      padding: 0, 
      display: "flex", 
      flexDirection: "column" 
    }}>
      
      {isAgentThinking && (
        <AgentThinking tripId={Number(tripId)} onComplete={() => loadWorkspace()} />
      )}

      {/* FULLSCREEN MAP */}
      <div style={{ position: "absolute", inset: 0 }}>
        <MapPanel 
          map={workspace.map} 
          selectedPlaceId={selectedPlaceId}
          activeDay={activeDay} 
          onPlaceClick={(id) => setSelectedPlaceId(id)} 
          baseLat={workspace.trip.accommodation_lat || 0}
          baseLng={workspace.trip.accommodation_lng || 0}
        />
      </div>

      {/* LEFT SIDEBAR (ITINERARY) */}
      <aside style={{
        position: "absolute", top: "1rem", left: "1rem", bottom: "1rem", zIndex: 30,
        width: "380px", background: "rgba(15, 23, 42, 0.8)", backdropFilter: "blur(20px)",
        borderRadius: "1.5rem", border: "1px solid rgba(255,255,255,0.1)", color: "white",
        display: "flex", flexDirection: "column", boxShadow: "0 25px 50px -12px rgba(0,0,0,0.5)",
        overflow: "hidden"
      }}>
        <div style={{ padding: "1.5rem", borderBottom: "1px solid rgba(255,255,255,0.1)" }}>
          <h1 style={{ fontSize: "1.4rem", fontWeight: 700, margin: 0 }}>{workspace.trip.destination}</h1>
          <p style={{ margin: "0.4rem 0 0", opacity: 0.6, fontSize: "0.85rem" }}>
            {workspace.trip.start_date} — {workspace.trip.end_date}
          </p>
          <div style={{ marginTop: "1rem", display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
            <button onClick={() => setActiveDay("all")} style={{
              padding: "0.4rem 0.8rem", borderRadius: "0.8rem", border: "none", fontSize: "0.8rem", cursor: "pointer",
              background: activeDay === "all" ? "var(--primary)" : "rgba(255,255,255,0.05)", color: "white"
            }}>Todos</button>
            {dates.sort().map((d, i) => (
              <button key={d} onClick={() => setActiveDay(d)} style={{
                padding: "0.4rem 0.8rem", borderRadius: "0.8rem", border: "none", fontSize: "0.8rem", cursor: "pointer",
                background: activeDay === d ? "var(--primary)" : "rgba(255,255,255,0.05)", color: "white"
              }}>Dia {i + 1}</button>
            ))}
          </div>
        </div>

        <div style={{ flex: 1, overflowY: "auto", padding: "1rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
          {workspace.map.markers
            .filter(m => (!activeDay || activeDay === "all" || m.date === activeDay) && m.kind !== "accommodation") // Hide accommodation from list
            .sort((a, b) => (a.start_time || "").localeCompare(b.start_time || ""))
            .map((marker) => (
              <div key={marker.id} 
                onClick={() => setSelectedPlaceId(marker.id)}
                style={{
                  padding: "1rem", borderRadius: "1.2rem", 
                  background: selectedPlaceId === marker.id ? "rgba(255,255,255,0.15)" : "rgba(255,255,255,0.03)",
                  border: `1px solid ${selectedPlaceId === marker.id ? "var(--primary)" : "rgba(255,255,255,0.05)"}`,
                  boxShadow: selectedPlaceId === marker.id ? "0 0 20px rgba(0, 255, 65, 0.15)" : "none",
                  cursor: "pointer", transition: "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)"
                }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.5rem" }}>
                   <div style={{ flex: 1 }}>
                     <strong style={{ fontSize: "0.95rem", color: selectedPlaceId === marker.id ? "var(--primary)" : "white", display: "block" }}>{marker.title}</strong>
                     <div style={{ display: "flex", gap: "0.4rem", marginTop: "0.2rem", alignItems: "center" }}>
                        <span style={{ fontSize: "0.65rem", opacity: 0.6, textTransform: "uppercase", letterSpacing: "0.5px" }}>{marker.kind}</span>
                        {marker.rating && <span style={{ fontSize: "0.7rem", color: "#f1c40f" }}>★ {marker.rating}</span>}
                     </div>
                   </div>
                   {marker.start_time && <span style={{ fontSize: "0.75rem", background: "rgba(0,255,65,0.1)", color: "#00ff41", padding: "2px 8px", borderRadius: "6px", fontWeight: 600, whiteSpace: "nowrap" }}>{marker.start_time}</span>}
                </div>
                <p style={{ fontSize: "0.75rem", opacity: 0.5, marginTop: "0.6rem", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden", lineHeight: 1.4 }}>
                  {marker.summary}
                </p>
              </div>
            ))}
            {workspace.map.markers.filter(m => (!activeDay || activeDay === "all" || m.date === activeDay) && m.kind !== "accommodation").length === 0 && (
              <p style={{ textAlign: "center", opacity: 0.4, marginTop: "2rem", fontSize: "0.9rem" }}>Nenhuma atração{activeDay !== "all" ? " para este dia" : ""} planejada.</p>
            )}
        </div>

        {/* CHAT AT SIDEBAR BOTTOM */}
        <div style={{ padding: "1rem", borderTop: "1px solid rgba(255,255,255,0.1)", background: "rgba(0,0,0,0.2)" }}>
           <form onSubmit={handleChatSubmit} style={{ display: "flex", gap: "0.5rem" }}>
             <input 
               type="text" 
               value={composerText} 
               onChange={e => setComposerText(e.target.value)} 
               placeholder="Ajustar roteiro..."
               style={{ flex: 1, background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: "0.8rem", color: "white", padding: "0.6rem 1rem", outline: "none", fontSize: "0.9rem" }}
             />
             <button type="submit" disabled={busyMessage} style={{
               background: "var(--primary)", color: "white", border: "none", borderRadius: "0.8rem",
               width: "40px", height: "40px", display: "grid", placeItems: "center", cursor: "pointer"
             }}>
               {busyMessage ? "..." : "→"}
             </button>
           </form>
        </div>
      </aside>

      {/* Accommodation/Hotel Summary Bubble (Top Right) */}
      {workspace.trip.accommodation_name && (
        <div style={{
          position: "absolute", top: "1.5rem", right: "1.5rem", zIndex: 10,
          background: "rgba(15, 23, 42, 0.9)", backdropFilter: "blur(20px)",
          padding: "0.8rem 1.2rem", borderRadius: "2rem", color: "white",
          display: "flex", alignItems: "center", gap: "0.8rem", fontSize: "0.85rem",
          border: "1px solid rgba(255, 255, 255, 0.1)",
          boxShadow: "0 10px 25px rgba(0,0,0,0.4)"
        }}>
          <span style={{ fontSize: "1.2rem" }}>🏠</span>
          <div style={{ lineHeight: 1.2 }}>
            <span style={{ opacity: 0.6, fontSize: "0.65rem", display: "block", textTransform: "uppercase", fontWeight: 700, letterSpacing: "1px" }}>Hospedagem</span>
            <strong style={{ fontSize: "0.9rem" }}>{workspace.trip.accommodation_name}</strong>
          </div>
        </div>
      )}

      {/* FLOATING PLACE INFO PANEL (RIGHT SIDE) */}
      {selectedPlaceId && selectedMarker && (
        <div style={{
          position: "absolute", top: "1rem", right: "1rem", zIndex: 20,
          width: "340px", background: "rgba(15, 23, 42, 0.95)", backdropFilter: "blur(20px)",
          borderRadius: "1.5rem", color: "white", overflow: "hidden",
          boxShadow: "0 30px 60px -12px rgba(0,0,0,0.7)",
          display: "flex", flexDirection: "column", maxHeight: "calc(100vh - 8rem)",
          border: "1px solid rgba(255,255,255,0.1)"
        }}>
          {selectedMarker.image_url && (
            <div style={{ position: "relative" }}>
              <img src={selectedMarker.image_url} alt={selectedMarker.title} style={{ width: "100%", height: "220px", objectFit: "cover" }} />
              <div style={{ position: "absolute", bottom: 0, left: 0, right: 0, height: "80px", background: "linear-gradient(to top, rgba(15,23,42,1), transparent)" }} />
            </div>
          )}
          <div style={{ padding: "1.5rem", marginTop: selectedMarker.image_url ? "-1.5rem" : "0", position: "relative", overflowY: "auto" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "0.8rem" }}>
              <h2 style={{ margin: 0, fontSize: "1.3rem", fontWeight: 700 }}>{selectedMarker.title}</h2>
              <button 
                onClick={() => setSelectedPlaceId(null)}
                style={{ 
                  background: "rgba(255,255,255,0.05)", border: "none", color: "white", cursor: "pointer", 
                  width: "32px", height: "32px", borderRadius: "50%", display: "grid", placeItems: "center",
                  fontSize: "1.2rem", transition: "background 0.2s"
                }}
                onMouseOver={e => e.currentTarget.style.background = "rgba(255,255,255,0.15)"}
                onMouseOut={e => e.currentTarget.style.background = "rgba(255,255,255,0.05)"}
              >×</button>
            </div>
            
            <div style={{ display: "flex", gap: "0.6rem", alignItems: "center", marginBottom: "1.2rem" }}>
               <span style={{ display: "inline-block", background: "rgba(255,255,255,0.1)", padding: "0.3rem 0.8rem", borderRadius: "1rem", fontSize: "0.75rem", fontWeight: 500, opacity: 0.9 }}>
                 {selectedMarker.kind}
               </span>
               {selectedMarker.price_level && (
                 <span style={{ color: "#f1c40f", fontSize: "0.9rem", fontWeight: 800 }}>
                   {"$".repeat(selectedMarker.price_level)}
                 </span>
               )}
            </div>

            {selectedMarker.rating && (
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "1.5rem", background: "rgba(255,255,255,0.03)", padding: "0.6rem 1rem", borderRadius: "1rem" }}>
                <span style={{ color: "#f1c40f", fontSize: "1.2rem" }}>★</span>
                <strong style={{ fontSize: "1.1rem" }}>{selectedMarker.rating}</strong>
                <span style={{ opacity: 0.5, fontSize: "0.8rem" }}>({selectedMarker.user_ratings_total?.toLocaleString()} avaliações)</span>
              </div>
            )}

            <div style={{ marginBottom: "1.5rem" }}>
              <p style={{ fontSize: "0.95rem", lineHeight: 1.6, opacity: 0.9, whiteSpace: "pre-wrap", color: "rgba(255,255,255,0.9)" }}>
                {selectedMarker.editorial_note || selectedMarker.summary || "Explora as maravilhas deste local único selecionado estrategicamente para sua viagem."}
              </p>
            </div>

            {selectedMarker.curator_reasoning && (
              <div style={{ 
                marginBottom: "1.5rem", padding: "1.2rem", 
                background: "rgba(0, 255, 65, 0.05)", 
                borderRadius: "1rem", 
                borderLeft: "4px solid var(--primary)",
                boxShadow: "inset 0 0 20px rgba(0,255,65,0.02)"
              }}>
                <strong style={{ display: "block", color: "var(--primary)", fontSize: "0.7rem", textTransform: "uppercase", marginBottom: "0.5rem", letterSpacing: "1px", fontWeight: 800 }}>
                  Por que indicamos?
                </strong>
                <p style={{ margin: 0, fontSize: "0.85rem", opacity: 0.9, fontStyle: "italic", lineHeight: 1.5 }}>
                  "{selectedMarker.curator_reasoning}"
                </p>
              </div>
            )}

            {selectedMarker.address_full && (
               <div style={{ marginBottom: "1rem", fontSize: "0.85rem", opacity: 0.7, display: "flex", gap: "0.8rem", alignItems: "flex-start" }}>
                  <span style={{ fontSize: "1.1rem" }}>📍</span>
                  <span style={{ lineHeight: 1.4 }}>{selectedMarker.address_full}</span>
               </div>
            )}

            {selectedMarker.website && (
              <a href={selectedMarker.website} target="_blank" rel="noreferrer" style={{ 
                display: "inline-flex", alignItems: "center", gap: "0.5rem", marginBottom: "1.5rem", 
                color: "var(--primary)", fontSize: "0.9rem", textDecoration: "none", fontWeight: 600,
                borderBottom: "1px dashed var(--primary)", paddingBottom: "2px"
              }}>
                🌐 Visitar Website
              </a>
            )}

            {selectedMarker.start_time && (
              <div style={{ 
                marginTop: "0.5rem", padding: "1rem 1.5rem", 
                background: "rgba(0,255,65,0.1)", 
                borderRadius: "1.2rem",
                display: "flex", justifyContent: "space-between", alignItems: "center"
              }}>
                <div>
                  <strong style={{ display: "block", color: "#00ff41", fontSize: "0.65rem", textTransform: "uppercase", letterSpacing: "1px", marginBottom: "0.2rem" }}>Horário Previsto</strong>
                  <span style={{ fontSize: "1.4rem", fontWeight: 700 }}>{selectedMarker.start_time}</span>
                </div>
                <div style={{ opacity: 0.3, fontSize: "1.5rem" }}>🕒</div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* DECISION OVERLAY */}
      {workspace.decisions.length > 0 && !isAgentThinking && (
        <div style={{
           position: "absolute", inset: 0, zIndex: 100, background: "rgba(15, 23, 42, 0.9)", backdropFilter: "blur(10px)",
           display: "flex", alignItems: "center", justifyContent: "center"
        }}>
           <div style={{ 
             background: "rgba(30, 41, 59, 0.8)", padding: "3rem", borderRadius: "2rem", maxWidth: "500px", 
             textAlign: "center", border: "1px solid rgba(255, 255, 255, 0.1)",
             boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.5)"
           }}>
             <h2 style={{ fontSize: "1.8rem", fontWeight: 800, marginBottom: "1rem" }}>Decisão Necessária</h2>
             <p style={{ fontSize: "1.1rem", marginBottom: "0.5rem" }}>{workspace.decisions[0].title}</p>
             <p style={{ opacity: 0.7, fontSize: "0.95rem", marginBottom: "2rem", lineHeight: 1.6 }}>{workspace.decisions[0].summary}</p>
             <div style={{ display: "flex", gap: "1rem", justifyContent: "center" }}>
                {workspace.decisions[0].options_json.map(opt => (
                  <button key={opt.id as string} 
                    onClick={async () => {
                      await api.decideWorkflow(tripId, workspace.decisions[0].id, { action: opt.id === "approve" ? "approve" : "reject" });
                      loadWorkspace();
                    }}
                    style={{
                      padding: "1rem 2rem", borderRadius: "1rem", border: "none", cursor: "pointer", 
                      fontSize: "1rem", fontWeight: 700, transition: "transform 0.2s, background 0.2s",
                      background: opt.id === "approve" ? "var(--primary)" : "rgba(255,255,255,0.1)",
                      color: opt.id === "approve" ? "black" : "white"
                    }}
                    onMouseOver={e => e.currentTarget.style.transform = "scale(1.05)"}
                    onMouseOut={e => e.currentTarget.style.transform = "scale(1)"}
                  >
                    {opt.label as string}
                  </button>
                ))}
             </div>
           </div>
        </div>
      )}
    </main>
  );
}
