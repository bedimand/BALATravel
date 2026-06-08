"use client";

import { useEffect, useRef, useState, useMemo, useCallback } from "react";
import type { CSSProperties, ReactNode } from "react";
import { api } from "@/lib/api";
import { useRequireAuth } from "@/lib/use-require-auth";
import type { WorkspaceResponse, AgentThread, Decision, MapResponse } from "@/lib/types";
import { AgentThinking } from "./agent-thinking";
import { MapPanel } from "./map-panel";
import { TripTimeline } from "./trip-timeline";

type Props = { tripId: string };

const QUICK_PROMPTS = [
  "Adicione mais restaurantes ao roteiro",
  "Reduza os deslocamentos do dia 2",
  "Inclua opções culturais e museus",
  "Ajuste para ritmo mais tranquilo",
  "Substitua atividades noturnas",
  "Otimize o roteiro por proximidade",
];

export function TripPlanner({ tripId }: Props) {
  useRequireAuth();
  const [workspace, setWorkspace] = useState<WorkspaceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeDay, setActiveDay] = useState<string | null>("all");
  const [selectedPlaceId, setSelectedPlaceId] = useState<string | null>(null);
  const [highlightIds, setHighlightIds] = useState<Set<string>>(new Set());
  const prevMarkerIdsRef = useRef<Set<string> | null>(null);
  const highlightTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [chatOpen, setChatOpen] = useState(false);
  const [chatInput, setChatInput] = useState("");
  const [chatBusy, setChatBusy] = useState(false);
  const [thread, setThread] = useState<AgentThread | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [decideBusy, setDecideBusy] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3000);
  };

  const loadWorkspace = useCallback(async () => {
    try {
      const w = await api.getWorkspace(tripId);
      setWorkspace(w);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [tripId]);

  const loadThread = useCallback(async () => {
    try {
      const t = await api.getAgentThread(tripId);
      setThread(t);
    } catch (e) {
      console.error(e);
    }
  }, [tripId]);

  useEffect(() => {
    loadWorkspace();
    loadThread();
  }, [loadWorkspace, loadThread]);

  const isAgentThinking = useMemo(
    () =>
      workspace?.workflow.stage_status === "running" ||
      workspace?.workflow_runs?.some((r) => r.status === "running"),
    [workspace]
  );

  useEffect(() => {
    if (isAgentThinking) {
      // Faster cadence during the build so pins/timeline feel live.
      pollRef.current = setInterval(async () => {
        await loadWorkspace();
        await loadThread();
      }, 3500);
    } else {
      if (pollRef.current) clearInterval(pollRef.current);
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [isAgentThinking, loadWorkspace, loadThread]);

  // Detect newly-arrived itinerary markers between workspace refreshes and flag them
  // so the timeline can animate them in. Only meaningful while the agent is building.
  useEffect(() => {
    const currentIds = new Set(
      (workspace?.map.markers ?? [])
        .filter((m) => m.kind !== "accommodation")
        .map((m) => m.id)
    );
    const prev = prevMarkerIdsRef.current;
    prevMarkerIdsRef.current = currentIds;

    if (!prev || !isAgentThinking) return;
    const fresh = [...currentIds].filter((id) => !prev.has(id));
    if (fresh.length === 0) return;

    setHighlightIds((curr) => {
      const next = new Set(curr);
      fresh.forEach((id) => next.add(id));
      return next;
    });
    if (highlightTimerRef.current) clearTimeout(highlightTimerRef.current);
    highlightTimerRef.current = setTimeout(() => setHighlightIds(new Set()), 2500);
  }, [workspace, isAgentThinking]);

  useEffect(() => {
    if (chatOpen) chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [thread, chatOpen]);

  const dates = useMemo(() => {
    if (!workspace) return [];
    return Array.from(
      new Set(workspace.map.markers.map((m) => m.date).filter(Boolean))
    ) as string[];
  }, [workspace]);

  const selectedMarker = useMemo(
    () => workspace?.map.markers.find((m) => m.id === selectedPlaceId),
    [workspace, selectedPlaceId]
  );

  async function sendChatMessage(message: string) {
    if (!message.trim() || chatBusy) return;
    setChatBusy(true);
    try {
      await api.sendWorkflowMessage(tripId, { message });
      setChatInput("");
      await loadWorkspace();
      await loadThread();
      showToast("Mensagem enviada! Agente processando...");
    } catch (e) {
      console.error(e);
      showToast("Erro ao enviar mensagem.");
    } finally {
      setChatBusy(false);
    }
  }

  if (loading && !workspace) {
    return (
      <div style={{
        background: "linear-gradient(135deg, #0a0f1e 0%, #111827 100%)",
        height: "100vh", color: "white", display: "grid", placeItems: "center"
      }}>
        <div style={{ textAlign: "center" }}>
          <div style={{
            width: "48px", height: "48px", border: "3px solid rgba(0,229,255,0.3)",
            borderTopColor: "#00e5ff", borderRadius: "50%", margin: "0 auto 1rem",
            animation: "spin 1s linear infinite"
          }} />
          <p style={{ opacity: 0.6, fontSize: "0.9rem" }}>Carregando roteiro...</p>
        </div>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  if (!workspace) return <div style={{ color: "white", padding: "2rem" }}>Falha ao carregar.</div>;

  const allRuns = thread?.runs ?? [];

  return (
    <main style={{
      position: "relative", height: "100dvh", overflow: "hidden",
      padding: 0, display: "flex", flexDirection: "column",
      background: "#0a0f1e"
    }}>
      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes fadeSlideUp { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
        @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }
        .day-btn:hover { background: rgba(255,255,255,0.12) !important; }
        .chat-bubble-in { animation: fadeSlideUp 0.25s ease both; }
        .quick-chip:hover { background: rgba(0,229,255,0.15) !important; border-color: rgba(0,229,255,0.5) !important; }
        .close-btn:hover { background: rgba(255,255,255,0.15) !important; }
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.15); border-radius: 4px; }
      `}</style>

      {isAgentThinking && (
        <AgentThinking tripId={Number(tripId)} onComplete={() => { loadWorkspace(); loadThread(); }} />
      )}

      {/* MAP */}
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

      {/* TOAST */}
      {toast && (
        <div style={{
          position: "absolute", top: "1rem", left: "50%", transform: "translateX(-50%)",
          zIndex: 200, background: "rgba(0,229,255,0.15)", backdropFilter: "blur(20px)",
          border: "1px solid rgba(0,229,255,0.4)", borderRadius: "2rem",
          color: "white", padding: "0.6rem 1.5rem", fontSize: "0.85rem",
          animation: "fadeSlideUp 0.3s ease both", whiteSpace: "nowrap"
        }}>
          {toast}
        </div>
      )}

      {/* LEFT SIDEBAR */}
      <aside style={{
        position: "absolute", top: "1rem", left: "1rem", bottom: "1rem", zIndex: 30,
        width: "360px", background: "rgba(10, 15, 30, 0.85)", backdropFilter: "blur(24px)",
        borderRadius: "1.5rem", border: "1px solid rgba(255,255,255,0.08)", color: "white",
        display: "flex", flexDirection: "column", boxShadow: "0 25px 60px -10px rgba(0,0,0,0.6)",
        overflow: "hidden", transition: "box-shadow 0.3s"
      }}>
        {/* Header */}
        <div style={{ padding: "1.25rem 1.5rem", borderBottom: "1px solid rgba(255,255,255,0.07)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
            <div>
              <h1 style={{ fontSize: "1.3rem", fontWeight: 800, margin: 0, letterSpacing: "-0.3px" }}>
                {workspace.trip.destination}
              </h1>
              <p style={{ margin: "0.3rem 0 0", opacity: 0.5, fontSize: "0.8rem" }}>
                {workspace.trip.start_date} — {workspace.trip.end_date}
              </p>
            </div>
            {isAgentThinking && (
              <span style={{
                fontSize: "0.7rem", background: "rgba(0,229,255,0.15)", color: "#00e5ff",
                padding: "0.3rem 0.7rem", borderRadius: "1rem", fontWeight: 700,
                animation: "pulse 1.5s ease infinite"
              }}>
                IA processando...
              </span>
            )}
          </div>

          {/* Day filters */}
          <div style={{ marginTop: "0.9rem", display: "flex", gap: "0.35rem", flexWrap: "wrap" }}>
            {["all", ...dates.sort()].map((d, i) => (
              <button
                key={d}
                className="day-btn"
                onClick={() => setActiveDay(d)}
                style={{
                  padding: "0.35rem 0.75rem", borderRadius: "0.7rem", border: "none",
                  fontSize: "0.75rem", cursor: "pointer", fontWeight: 600,
                  background: activeDay === d ? "#00e5ff" : "rgba(255,255,255,0.06)",
                  color: activeDay === d ? "#000" : "white",
                  transition: "all 0.2s ease"
                }}
              >
                {d === "all" ? "Todos" : `Dia ${i}`}
              </button>
            ))}
          </div>

        </div>

        {/* Itinerary body: the agenda timeline (enriched with place details) */}
        <div style={{ flex: 1, overflowY: "auto" }}>
          <TripTimeline
            markers={workspace.map.markers}
            dates={dates}
            activeDay={activeDay}
            selectedPlaceId={selectedPlaceId}
            onPlaceClick={(id) => setSelectedPlaceId(selectedPlaceId === id ? null : id)}
            highlightIds={highlightIds}
            compact
          />
        </div>

        {/* Chat toggle button (hidden while the agent is building) */}
        {!isAgentThinking && (
        <div style={{ padding: "0.75rem 1rem", borderTop: "1px solid rgba(255,255,255,0.07)" }}>
          <button
            onClick={() => setChatOpen((v) => !v)}
            style={{
              width: "100%", padding: "0.75rem 1rem", borderRadius: "1rem",
              background: chatOpen ? "rgba(0,229,255,0.12)" : "rgba(255,255,255,0.05)",
              border: `1px solid ${chatOpen ? "rgba(0,229,255,0.4)" : "rgba(255,255,255,0.08)"}`,
              color: chatOpen ? "#00e5ff" : "white", cursor: "pointer",
              display: "flex", alignItems: "center", justifyContent: "center", gap: "0.6rem",
              fontSize: "0.88rem", fontWeight: 600, transition: "all 0.2s ease"
            }}
          >
            <span style={{ fontSize: "1rem" }}>💬</span>
            {chatOpen ? "Fechar chat" : "Modificar roteiro com IA"}
            {allRuns.length > 0 && (
              <span style={{
                background: "#00e5ff", color: "#000", borderRadius: "1rem",
                fontSize: "0.65rem", padding: "1px 6px", fontWeight: 800
              }}>{allRuns.length}</span>
            )}
          </button>
        </div>
        )}
      </aside>

      {/* CHAT PANEL (right side, slides in) */}
      <aside style={{
        position: "absolute", top: "1rem", right: "1rem", bottom: "1rem", zIndex: 25,
        width: "380px", background: "rgba(10, 15, 30, 0.92)", backdropFilter: "blur(24px)",
        borderRadius: "1.5rem", border: "1px solid rgba(255,255,255,0.08)", color: "white",
        display: "flex", flexDirection: "column", boxShadow: "0 25px 60px -10px rgba(0,0,0,0.6)",
        overflow: "hidden",
        transform: chatOpen && !selectedPlaceId ? "translateX(0)" : "translateX(calc(100% + 1.5rem))",
        transition: "transform 0.35s cubic-bezier(0.4, 0, 0.2, 1)",
        pointerEvents: chatOpen && !selectedPlaceId ? "auto" : "none"
      }}>
        {/* Chat header */}
        <div style={{ padding: "1.25rem 1.5rem", borderBottom: "1px solid rgba(255,255,255,0.07)", display: "flex", alignItems: "center", gap: "0.8rem" }}>
          <span style={{ fontSize: "1.4rem" }}>🤖</span>
          <div style={{ flex: 1 }}>
            <h2 style={{ margin: 0, fontSize: "1rem", fontWeight: 700 }}>Assistente de Viagem</h2>
            <p style={{ margin: 0, fontSize: "0.72rem", opacity: 0.45 }}>Peça ajustes no seu roteiro</p>
          </div>
          {isAgentThinking && (
            <span style={{ fontSize: "0.65rem", color: "#00e5ff", animation: "pulse 1.5s infinite", fontWeight: 700 }}>
              Pensando...
            </span>
          )}
        </div>

        {/* Quick prompts */}
        <div style={{ padding: "0.75rem 1rem", borderBottom: "1px solid rgba(255,255,255,0.05)", display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
          {QUICK_PROMPTS.map((p) => (
            <button
              key={p}
              className="quick-chip"
              onClick={() => sendChatMessage(p)}
              disabled={chatBusy}
              style={{
                padding: "0.3rem 0.7rem", borderRadius: "1rem", cursor: "pointer",
                background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.1)",
                color: "rgba(255,255,255,0.75)", fontSize: "0.72rem", transition: "all 0.2s ease"
              }}
            >
              {p}
            </button>
          ))}
        </div>

        {/* Messages */}
        <div style={{ flex: 1, overflowY: "auto", padding: "1rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
          {allRuns.length === 0 ? (
            <div style={{ textAlign: "center", opacity: 0.3, marginTop: "3rem" }}>
              <p style={{ fontSize: "2.5rem", marginBottom: "0.5rem" }}>✈️</p>
              <p style={{ fontSize: "0.85rem" }}>Nenhuma conversa ainda.<br />Peça uma modificação acima!</p>
            </div>
          ) : (
            allRuns.map((run) => (
              <div key={run.id} className="chat-bubble-in" style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                {run.user_message && (
                  <div style={{ display: "flex", justifyContent: "flex-end" }}>
                    <div style={{
                      background: "#00e5ff", color: "#000", padding: "0.65rem 1rem",
                      borderRadius: "1.2rem 1.2rem 0.3rem 1.2rem", maxWidth: "85%",
                      fontSize: "0.85rem", fontWeight: 500, lineHeight: 1.45
                    }}>
                      {run.user_message}
                    </div>
                  </div>
                )}
                {run.assistant_message && (
                  <div style={{ display: "flex", justifyContent: "flex-start", gap: "0.5rem" }}>
                    <span style={{ fontSize: "1.2rem", flexShrink: 0, marginTop: "2px" }}>🤖</span>
                    <div style={{
                      background: "rgba(255,255,255,0.07)", padding: "0.65rem 1rem",
                      borderRadius: "0.3rem 1.2rem 1.2rem 1.2rem", maxWidth: "85%",
                      fontSize: "0.83rem", lineHeight: 1.55, opacity: 0.9
                    }}>
                      {run.assistant_message}
                    </div>
                  </div>
                )}
                {run.tool_calls?.length > 0 && (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "0.3rem", paddingLeft: "1.7rem" }}>
                    {run.tool_calls.map((call) => (
                      <span key={call.id} style={{
                        fontSize: "0.65rem", padding: "2px 7px", borderRadius: "0.5rem",
                        background: call.status === "success" ? "rgba(0,229,255,0.1)" : "rgba(255,100,100,0.1)",
                        color: call.status === "success" ? "#00e5ff" : "#ff6464",
                        border: `1px solid ${call.status === "success" ? "rgba(0,229,255,0.2)" : "rgba(255,100,100,0.2)"}`
                      }}>
                        {call.tool_name}
                      </span>
                    ))}
                  </div>
                )}
                {run.warnings?.length > 0 && (
                  <div style={{
                    marginLeft: "1.7rem", padding: "0.5rem 0.75rem", borderRadius: "0.7rem",
                    background: "rgba(255,200,0,0.08)", border: "1px solid rgba(255,200,0,0.2)", fontSize: "0.75rem", color: "#ffc800"
                  }}>
                    {run.warnings.map((w) => <p key={w} style={{ margin: "0.1rem 0" }}>⚠ {w}</p>)}
                  </div>
                )}
              </div>
            ))
          )}
          {chatBusy && (
            <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", opacity: 0.6 }}>
              <span style={{ fontSize: "1.2rem" }}>🤖</span>
              <div style={{ display: "flex", gap: "4px" }}>
                {[0, 1, 2].map((i) => (
                  <span key={i} style={{
                    width: "6px", height: "6px", background: "#00e5ff", borderRadius: "50%",
                    animation: `pulse 1s ease ${i * 0.2}s infinite`
                  }} />
                ))}
              </div>
            </div>
          )}
          <div ref={chatEndRef} />
        </div>

        {/* Chat input */}
        <div style={{ padding: "0.85rem 1rem", borderTop: "1px solid rgba(255,255,255,0.07)" }}>
          <form
            onSubmit={(e) => { e.preventDefault(); sendChatMessage(chatInput); }}
            style={{ display: "flex", gap: "0.5rem", alignItems: "flex-end" }}
          >
            <textarea
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  sendChatMessage(chatInput);
                }
              }}
              placeholder="Ex: Adicione um jantar romântico no dia 2..."
              rows={2}
              style={{
                flex: 1, background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)",
                borderRadius: "0.9rem", color: "white", padding: "0.65rem 1rem", outline: "none",
                fontSize: "0.85rem", resize: "none", lineHeight: 1.4, fontFamily: "inherit",
                transition: "border-color 0.2s"
              }}
              onFocus={(e) => e.target.style.borderColor = "rgba(0,229,255,0.4)"}
              onBlur={(e) => e.target.style.borderColor = "rgba(255,255,255,0.1)"}
            />
            <button
              type="submit"
              disabled={chatBusy || !chatInput.trim()}
              style={{
                background: chatBusy || !chatInput.trim() ? "rgba(255,255,255,0.1)" : "#00e5ff",
                color: chatBusy || !chatInput.trim() ? "rgba(255,255,255,0.4)" : "#000",
                border: "none", borderRadius: "0.9rem", width: "42px", height: "42px",
                display: "grid", placeItems: "center", cursor: chatBusy ? "not-allowed" : "pointer",
                fontSize: "1.1rem", transition: "all 0.2s ease", flexShrink: 0
              }}
            >
              {chatBusy ? (
                <span style={{ width: "16px", height: "16px", border: "2px solid rgba(255,255,255,0.3)", borderTopColor: "white", borderRadius: "50%", display: "block", animation: "spin 0.8s linear infinite" }} />
              ) : "↑"}
            </button>
          </form>
          <p style={{ margin: "0.4rem 0 0", fontSize: "0.65rem", opacity: 0.3, textAlign: "center" }}>
            Enter para enviar · Shift+Enter para nova linha
          </p>
        </div>
      </aside>

      {/* ACCOMMODATION BADGE */}
      {workspace.trip.accommodation_name && !chatOpen && !isAgentThinking && (
        <div style={{
          position: "absolute", top: "1.5rem", right: "1.5rem", zIndex: 10,
          background: "rgba(10, 15, 30, 0.9)", backdropFilter: "blur(20px)",
          padding: "0.7rem 1.1rem", borderRadius: "2rem", color: "white",
          display: "flex", alignItems: "center", gap: "0.7rem", fontSize: "0.83rem",
          border: "1px solid rgba(255,255,255,0.08)",
          boxShadow: "0 10px 25px rgba(0,0,0,0.4)", animation: "fadeIn 0.3s ease"
        }}>
          <span>🏠</span>
          <div style={{ lineHeight: 1.2 }}>
            <span style={{ opacity: 0.5, fontSize: "0.6rem", display: "block", textTransform: "uppercase", fontWeight: 700, letterSpacing: "1px" }}>Hospedagem</span>
            <strong style={{ fontSize: "0.88rem" }}>{workspace.trip.accommodation_name}</strong>
          </div>
        </div>
      )}

      {/* PLACE DETAIL PANEL */}
      {selectedPlaceId && selectedMarker && !isAgentThinking && (
        <div style={{
          position: "absolute", top: "1rem", right: "1rem", zIndex: 35,
          width: "340px", background: "rgba(10, 15, 30, 0.97)", backdropFilter: "blur(24px)",
          borderRadius: "1.5rem", color: "white", overflow: "hidden",
          boxShadow: "0 30px 60px -12px rgba(0,0,0,0.8)",
          display: "flex", flexDirection: "column", maxHeight: "calc(100vh - 2rem)",
          border: "1px solid rgba(255,255,255,0.1)",
          animation: "fadeSlideUp 0.25s ease both"
        }}>
          {selectedMarker.image_url && (
            <div style={{ position: "relative", flexShrink: 0 }}>
              <img
                src={selectedMarker.image_url}
                alt={selectedMarker.title}
                style={{ width: "100%", height: "200px", objectFit: "cover" }}
              />
              <div style={{ position: "absolute", bottom: 0, left: 0, right: 0, height: "80px", background: "linear-gradient(to top, rgba(10,15,30,1), transparent)" }} />
            </div>
          )}
          <div style={{ padding: "1.25rem", overflowY: "auto", flex: 1 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "0.75rem" }}>
              <h2 style={{ margin: 0, fontSize: "1.2rem", fontWeight: 800, lineHeight: 1.3 }}>{selectedMarker.title}</h2>
              <button
                className="close-btn"
                onClick={() => setSelectedPlaceId(null)}
                style={{
                  background: "rgba(255,255,255,0.05)", border: "none", color: "white",
                  cursor: "pointer", width: "30px", height: "30px", borderRadius: "50%",
                  display: "grid", placeItems: "center", fontSize: "1rem", flexShrink: 0,
                  transition: "background 0.2s"
                }}
              >×</button>
            </div>

            <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", marginBottom: "1rem", flexWrap: "wrap" }}>
              <span style={{ background: "rgba(255,255,255,0.08)", padding: "0.25rem 0.7rem", borderRadius: "1rem", fontSize: "0.72rem", fontWeight: 500 }}>
                {selectedMarker.kind}
              </span>
              {selectedMarker.rating && (
                <span style={{ display: "flex", alignItems: "center", gap: "0.3rem", background: "rgba(241,196,15,0.1)", padding: "0.25rem 0.7rem", borderRadius: "1rem", fontSize: "0.75rem" }}>
                  <span style={{ color: "#f1c40f" }}>★</span>
                  <strong>{selectedMarker.rating}</strong>
                  {selectedMarker.user_ratings_total && <span style={{ opacity: 0.5 }}>({selectedMarker.user_ratings_total.toLocaleString()})</span>}
                </span>
              )}
            </div>

            <p style={{ fontSize: "0.88rem", lineHeight: 1.6, opacity: 0.85, marginBottom: "1.25rem" }}>
              {selectedMarker.editorial_note || selectedMarker.summary}
            </p>

            {selectedMarker.curator_reasoning && (
              <div style={{
                marginBottom: "1.25rem", padding: "1rem",
                background: "rgba(0,229,255,0.05)", borderRadius: "1rem",
                borderLeft: "3px solid #00e5ff"
              }}>
                <strong style={{ display: "block", color: "#00e5ff", fontSize: "0.65rem", textTransform: "uppercase", letterSpacing: "1px", marginBottom: "0.4rem" }}>
                  Por que indicamos?
                </strong>
                <p style={{ margin: 0, fontSize: "0.82rem", opacity: 0.85, fontStyle: "italic", lineHeight: 1.5 }}>
                  "{selectedMarker.curator_reasoning}"
                </p>
              </div>
            )}

            {selectedMarker.address_full && (
              <div style={{ marginBottom: "0.9rem", fontSize: "0.82rem", opacity: 0.6, display: "flex", gap: "0.6rem" }}>
                <span>📍</span><span style={{ lineHeight: 1.4 }}>{selectedMarker.address_full}</span>
              </div>
            )}

            {selectedMarker.website && (
              <a href={selectedMarker.website} target="_blank" rel="noreferrer" style={{
                display: "inline-flex", alignItems: "center", gap: "0.4rem", marginBottom: "1.25rem",
                color: "#00e5ff", fontSize: "0.85rem", textDecoration: "none", fontWeight: 600
              }}>
                🌐 Visitar Website →
              </a>
            )}

            {selectedMarker.start_time && (
              <div style={{
                padding: "0.9rem 1.25rem", background: "rgba(0,229,255,0.08)",
                borderRadius: "1rem", display: "flex", justifyContent: "space-between", alignItems: "center",
                border: "1px solid rgba(0,229,255,0.15)"
              }}>
                <div>
                  <strong style={{ display: "block", color: "#00e5ff", fontSize: "0.6rem", textTransform: "uppercase", letterSpacing: "1px", marginBottom: "0.2rem" }}>Horário Previsto</strong>
                  <span style={{ fontSize: "1.4rem", fontWeight: 800 }}>{selectedMarker.start_time}</span>
                </div>
                <span style={{ opacity: 0.25, fontSize: "1.5rem" }}>🕒</span>
              </div>
            )}

            {/* Chat shortcut from place panel */}
            <button
              onClick={() => {
                setChatInput(`Substitua "${selectedMarker.title}" por uma opção similar`);
                setSelectedPlaceId(null);
                setChatOpen(true);
              }}
              style={{
                marginTop: "0.9rem", width: "100%", padding: "0.7rem",
                background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)",
                borderRadius: "0.9rem", color: "rgba(255,255,255,0.6)", cursor: "pointer",
                fontSize: "0.78rem", transition: "all 0.2s ease"
              }}
              onMouseOver={(e) => { e.currentTarget.style.background = "rgba(0,229,255,0.08)"; e.currentTarget.style.color = "#00e5ff"; }}
              onMouseOut={(e) => { e.currentTarget.style.background = "rgba(255,255,255,0.04)"; e.currentTarget.style.color = "rgba(255,255,255,0.6)"; }}
            >
              💬 Pedir substituição ao assistente
            </button>
          </div>
        </div>
      )}

      {/* DECISION CARD — lightweight, non-blocking suggestion popup */}
      {workspace.decisions.length > 0 && !isAgentThinking && (
        <DecisionCard
          decision={workspace.decisions[0]}
          markers={workspace.map.markers}
          decideBusy={decideBusy}
          onDecide={async (action) => {
            setDecideBusy(true);
            try {
              await api.decideWorkflow(tripId, workspace.decisions[0].id, { action });
              await loadWorkspace();
              showToast(action === "approve" ? "Mudança aplicada ✓" : "Sugestão descartada");
            } catch (e) {
              console.error(e);
              showToast("Erro ao processar decisão.");
            } finally {
              setDecideBusy(false);
            }
          }}
        />
      )}
    </main>
  );
}

type ProposalChange = {
  type?: string;
  title?: string;
  reason?: string;
  payload?: Record<string, unknown>;
};

function fmtTime(value: unknown): string {
  const text = String(value ?? "").trim();
  if (!text) return "";
  // Accept "09:00", "09:00:00" → "09:00"
  const match = text.match(/^(\d{1,2}):(\d{2})/);
  return match ? `${match[1].padStart(2, "0")}:${match[2]}` : text;
}

/**
 * A compact suggestion card (bottom-right) that shows exactly WHAT the assistant
 * wants to change — a before→after diff for single items, a day overview for a
 * full-day replan — instead of a blocking full-screen "decision required" wall.
 */
function DecisionCard({
  decision,
  markers,
  decideBusy,
  onDecide,
}: {
  decision: Decision;
  markers: MapResponse["markers"];
  decideBusy: boolean;
  onDecide: (action: "approve" | "reject") => void;
}) {
  const proposal: ProposalChange = decision.payload_json?.proposal ?? {};
  const payload = (proposal.payload ?? {}) as Record<string, unknown>;
  const type = proposal.type;

  // For a single-item edit, find the current item so we can show before→after.
  const current =
    type === "update_item" && payload.item_id != null
      ? markers.find((m) => m.id === `item-${payload.item_id}`)
      : undefined;

  let body: ReactNode;
  if (type === "update_item") {
    const afterTitle = (payload.title as string) || current?.title || "";
    const afterStart = fmtTime(payload.start_time);
    const afterEnd = fmtTime(payload.end_time);
    const afterTime = afterStart && afterEnd ? `${afterStart}–${afterEnd}` : "";
    const beforeTime =
      current?.start_time ? fmtTime(current.start_time) : "";
    body = (
      <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        {current && (
          <div style={diffRowStyle("before")}>
            <span style={diffTagStyle("before")}>Atual</span>
            <span style={{ opacity: 0.7, textDecoration: "line-through" }}>
              {beforeTime && <strong style={{ marginRight: 6 }}>{beforeTime}</strong>}
              {current.title}
            </span>
          </div>
        )}
        <div style={diffRowStyle("after")}>
          <span style={diffTagStyle("after")}>Novo</span>
          <span>
            {afterTime && <strong style={{ marginRight: 6, color: "#00e5ff" }}>{afterTime}</strong>}
            {afterTitle}
          </span>
        </div>
        {payload.notes ? (
          <p style={{ margin: "0.2rem 0 0", fontSize: "0.78rem", opacity: 0.6, lineHeight: 1.5 }}>
            {String(payload.notes)}
          </p>
        ) : null}
      </div>
    );
  } else if (type === "set_day") {
    const items = Array.isArray(payload.items) ? (payload.items as Record<string, unknown>[]) : [];
    const dateText = String(payload.date ?? "");
    body = (
      <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
        <div style={{ fontSize: "0.8rem", opacity: 0.75 }}>
          Novo plano para <strong>{dateText}</strong> · {items.length} atividade{items.length === 1 ? "" : "s"}
        </div>
        <ol style={{ margin: 0, padding: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: "0.3rem" }}>
          {items.slice(0, 5).map((it, i) => (
            <li key={i} style={{ fontSize: "0.8rem", display: "flex", gap: "0.5rem", alignItems: "baseline" }}>
              <strong style={{ color: "#00e5ff", minWidth: 42 }}>{fmtTime(it.start_time)}</strong>
              <span style={{ opacity: 0.9 }}>{String(it.title ?? "")}</span>
            </li>
          ))}
          {items.length > 5 && (
            <li style={{ fontSize: "0.75rem", opacity: 0.5 }}>+{items.length - 5} mais…</li>
          )}
        </ol>
      </div>
    );
  } else if (type === "generate_itinerary") {
    body = (
      <p style={{ margin: 0, fontSize: "0.82rem", opacity: 0.75, lineHeight: 1.5 }}>
        Refazer o roteiro completo do zero com base nas novas preferências.
      </p>
    );
  } else {
    // Fallback: no structured proposal available — show the summary text.
    body = (
      <p style={{ margin: 0, fontSize: "0.82rem", opacity: 0.75, lineHeight: 1.5 }}>
        {decision.summary}
      </p>
    );
  }

  const reason = proposal.reason || decision.summary;
  const heading = proposal.title || decision.title;

  return (
    <div
      style={{
        position: "absolute", right: "1.5rem", bottom: "1.5rem", zIndex: 100,
        width: "min(380px, calc(100% - 3rem))",
        background: "rgba(18, 26, 44, 0.97)",
        border: "1px solid rgba(0,229,255,0.25)",
        borderRadius: "1.1rem",
        boxShadow: "0 20px 45px -15px rgba(0,0,0,0.7)",
        padding: "1.1rem 1.2rem",
        color: "white",
        animation: "fadeSlideUp 0.25s ease both",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "0.45rem", marginBottom: "0.7rem" }}>
        <span style={{ fontSize: "1rem" }}>✨</span>
        <span style={{ fontSize: "0.72rem", fontWeight: 700, letterSpacing: "0.04em", textTransform: "uppercase", opacity: 0.55 }}>
          Sugestão do assistente
        </span>
      </div>

      <p style={{ margin: "0 0 0.65rem", fontSize: "0.95rem", fontWeight: 700, lineHeight: 1.35 }}>{heading}</p>

      <div style={{
        background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.06)",
        borderRadius: "0.75rem", padding: "0.7rem 0.8rem", marginBottom: "0.7rem"
      }}>
        {body}
      </div>

      {reason && heading !== reason && (
        <p style={{ margin: "0 0 0.85rem", fontSize: "0.78rem", opacity: 0.55, lineHeight: 1.5 }}>{reason}</p>
      )}

      <div style={{ display: "flex", gap: "0.55rem", justifyContent: "flex-end" }}>
        <button
          onClick={() => onDecide("reject")}
          disabled={decideBusy}
          style={{
            padding: "0.55rem 1.1rem", borderRadius: "0.7rem", border: "1px solid rgba(255,255,255,0.12)",
            cursor: decideBusy ? "default" : "pointer", fontSize: "0.82rem", fontWeight: 600,
            background: "transparent", color: "rgba(255,255,255,0.7)", opacity: decideBusy ? 0.5 : 1,
            transition: "all 0.15s ease",
          }}
          onMouseOver={(e) => { if (!decideBusy) e.currentTarget.style.background = "rgba(255,255,255,0.06)"; }}
          onMouseOut={(e) => { e.currentTarget.style.background = "transparent"; }}
        >
          Descartar
        </button>
        <button
          onClick={() => onDecide("approve")}
          disabled={decideBusy}
          style={{
            padding: "0.55rem 1.3rem", borderRadius: "0.7rem", border: "none",
            cursor: decideBusy ? "default" : "pointer", fontSize: "0.82rem", fontWeight: 700,
            background: "#00e5ff", color: "#000", opacity: decideBusy ? 0.5 : 1,
            transition: "all 0.15s ease",
          }}
          onMouseOver={(e) => { if (!decideBusy) e.currentTarget.style.transform = "scale(1.04)"; }}
          onMouseOut={(e) => { e.currentTarget.style.transform = "scale(1)"; }}
        >
          {decideBusy ? "…" : "Aplicar"}
        </button>
      </div>
    </div>
  );
}

function diffRowStyle(kind: "before" | "after"): CSSProperties {
  return {
    display: "flex", alignItems: "baseline", gap: "0.5rem",
    fontSize: "0.84rem", lineHeight: 1.4,
    color: kind === "before" ? "rgba(255,255,255,0.7)" : "white",
  };
}

function diffTagStyle(kind: "before" | "after"): CSSProperties {
  return {
    flexShrink: 0, fontSize: "0.62rem", fontWeight: 700, textTransform: "uppercase",
    letterSpacing: "0.04em", padding: "0.12rem 0.4rem", borderRadius: "0.4rem",
    background: kind === "before" ? "rgba(255,255,255,0.08)" : "rgba(0,229,255,0.15)",
    color: kind === "before" ? "rgba(255,255,255,0.6)" : "#00e5ff",
  };
}
