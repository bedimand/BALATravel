"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { AgentStatusResponse, AgentStep } from "@/lib/types";

// Map a step's key to a friendly icon + label for the activity feed.
function describeStep(step: AgentStep): { icon: string; label: string } {
  const key = step.step_key;
  if (key.startsWith("search")) return { icon: "🔍", label: "Buscando lugares" };
  if (key.includes("weather")) return { icon: "🌤", label: "Conferindo o clima" };
  if (key.startsWith("place_item")) return { icon: "📍", label: "Adicionando parada" };
  if (key.startsWith("start_itinerary")) return { icon: "🗓", label: "Iniciando roteiro" };
  if (key.startsWith("set_day")) return { icon: "📐", label: "Organizando o dia" };
  if (key.startsWith("get_day")) return { icon: "🧭", label: "Analisando o dia" };
  if (key.startsWith("list_saved_places")) return { icon: "📚", label: "Revisando opções" };
  if (key.startsWith("finalize")) return { icon: "✅", label: "Finalizando roteiro" };
  if (key === "agent_thought") return { icon: "💭", label: "Pensando" };
  if (key === "agent_finish") return { icon: "🏁", label: "Concluído" };
  if (step.status === "failed") return { icon: "⚠️", label: "Ajustando rota" };
  return { icon: "⚙️", label: "Processando" };
}

export function AgentThinking({ tripId, onComplete }: { tripId: number; onComplete: () => void }) {
  const [status, setStatus] = useState<AgentStatusResponse | null>(null);
  const feedEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let pollingId: NodeJS.Timeout;

    async function poll() {
      try {
        const data = await api.getAgentStatus(tripId);
        setStatus(data);

        if (data.status === "completed" || data.status === "failed") {
          setTimeout(() => {
            onComplete();
          }, 1500);
        } else {
          pollingId = setTimeout(poll, 1500);
        }
      } catch (e) {
        console.error("Agent status polling failed", e);
        pollingId = setTimeout(poll, 3000);
      }
    }

    poll();
    return () => clearTimeout(pollingId);
  }, [tripId, onComplete]);

  // Keep the newest step in view as the feed grows.
  useEffect(() => {
    feedEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [status?.steps.length]);

  const progress = status?.progress_percent ?? 0;
  const steps = status?.steps ?? [];

  return (
    <>
      {/* TOP PROGRESS BAR */}
      <div style={{
        position: "absolute", top: "1rem", left: "50%", transform: "translateX(-50%)", zIndex: 60,
        width: "min(520px, calc(100% - 2rem))",
        background: "rgba(10, 15, 30, 0.9)", backdropFilter: "blur(20px)",
        border: "1px solid rgba(0,229,255,0.25)", borderRadius: "1.25rem",
        boxShadow: "0 20px 50px -12px rgba(0,0,0,0.7)", color: "white",
        padding: "0.85rem 1.15rem", animation: "fadeSlideDown 0.35s ease both",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <div className="agent-pulse" style={{
            width: "2.1rem", height: "2.1rem", borderRadius: "50%", flexShrink: 0,
            background: "rgba(0,229,255,0.12)", display: "grid", placeItems: "center",
          }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#00e5ff" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 22s-8-4.5-8-11.8A8 8 0 0 1 12 2a8 8 0 0 1 8 8.2c0 7.3-8 11.8-8 11.8z" />
              <circle cx="12" cy="10" r="3" />
            </svg>
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "0.5rem" }}>
              <strong style={{ fontSize: "0.85rem", fontFamily: "var(--font-display)" }}>Construindo seu roteiro…</strong>
              <span style={{ fontSize: "0.72rem", color: "#00e5ff", fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>
                {Math.round(progress)}%
              </span>
            </div>
            <p style={{
              margin: "0.1rem 0 0", fontSize: "0.7rem", color: "var(--muted)",
              whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
            }}>
              {status?.current_step_summary || "Iniciando camada de inteligência…"}
            </p>
          </div>
        </div>
        <div style={{ marginTop: "0.6rem", width: "100%", height: "4px", background: "rgba(255,255,255,0.08)", borderRadius: "2px", overflow: "hidden" }}>
          <div style={{
            width: `${progress}%`, height: "100%",
            background: "linear-gradient(90deg, var(--primary), var(--accent))",
            transition: "width 1s cubic-bezier(0.4, 0, 0.2, 1)",
          }} />
        </div>
      </div>

      {/* RIGHT-SIDE AGENT ACTIVITY FEED */}
      <aside style={{
        position: "absolute", top: "1rem", right: "1rem", bottom: "1rem", zIndex: 55,
        width: "320px", background: "rgba(10, 15, 30, 0.9)", backdropFilter: "blur(24px)",
        borderRadius: "1.5rem", border: "1px solid rgba(255,255,255,0.08)", color: "white",
        display: "flex", flexDirection: "column", boxShadow: "0 25px 60px -10px rgba(0,0,0,0.6)",
        overflow: "hidden", animation: "fadeSlideLeft 0.35s ease both",
      }}>
        <div style={{ padding: "1.1rem 1.25rem", borderBottom: "1px solid rgba(255,255,255,0.07)", display: "flex", alignItems: "center", gap: "0.65rem" }}>
          <span style={{ fontSize: "1.25rem" }}>🤖</span>
          <div style={{ flex: 1 }}>
            <h2 style={{ margin: 0, fontSize: "0.92rem", fontWeight: 700 }}>Agente de Viagem</h2>
            <p style={{ margin: 0, fontSize: "0.68rem", opacity: 0.45 }}>Acompanhe cada passo em tempo real</p>
          </div>
        </div>

        <div style={{ flex: 1, overflowY: "auto", padding: "0.85rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          {steps.length === 0 ? (
            <div style={{ textAlign: "center", opacity: 0.4, marginTop: "2.5rem", fontSize: "0.8rem" }}>
              <div className="agent-pulse" style={{
                width: "2.5rem", height: "2.5rem", borderRadius: "50%", margin: "0 auto 0.85rem",
                background: "rgba(0,229,255,0.12)",
              }} />
              Iniciando camada de inteligência…
            </div>
          ) : (
            steps.map((step, idx) => {
              const isLast = idx === steps.length - 1;
              const { icon, label } = describeStep(step);
              const dotColor =
                step.status === "completed" ? "var(--primary)" :
                step.status === "failed" ? "var(--danger)" : "var(--warning)";
              return (
                <div
                  key={`${step.step_key}-${idx}`}
                  className="feed-row"
                  style={{
                    padding: "0.65rem 0.8rem", borderRadius: "0.85rem",
                    background: isLast ? "var(--primary-soft)" : "rgba(255,255,255,0.03)",
                    border: `1px solid ${isLast ? "rgba(0,229,255,0.3)" : "rgba(255,255,255,0.05)"}`,
                    display: "flex", gap: "0.6rem", alignItems: "flex-start",
                  }}
                >
                  <span style={{ fontSize: "0.95rem", lineHeight: 1.3, flexShrink: 0 }}>{icon}</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                      <span style={{
                        width: "6px", height: "6px", borderRadius: "50%", background: dotColor,
                        boxShadow: step.status === "running" ? `0 0 8px ${dotColor}` : "none", flexShrink: 0,
                      }} />
                      <strong style={{ fontSize: "0.72rem", letterSpacing: "0.2px", color: isLast ? "#00e5ff" : "rgba(255,255,255,0.9)" }}>
                        {label}
                      </strong>
                    </div>
                    <p style={{ margin: "0.2rem 0 0", fontSize: "0.74rem", lineHeight: 1.4, opacity: 0.78 }}>
                      {step.summary}
                    </p>
                    {step.reasoning && (
                      <p style={{ margin: "0.2rem 0 0", fontSize: "0.68rem", lineHeight: 1.35, opacity: 0.5, fontStyle: "italic" }}>
                        {step.reasoning}
                      </p>
                    )}
                  </div>
                </div>
              );
            })
          )}
          <div ref={feedEndRef} />
        </div>
      </aside>

      <style dangerouslySetInnerHTML={{ __html: `
        @keyframes fadeSlideDown { from { opacity: 0; transform: translate(-50%, -12px); } to { opacity: 1; transform: translate(-50%, 0); } }
        @keyframes fadeSlideLeft { from { opacity: 0; transform: translateX(16px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes agentPulse {
          0% { box-shadow: 0 0 0 0 rgba(0, 229, 255, 0.4); }
          70% { box-shadow: 0 0 0 12px rgba(0, 229, 255, 0); }
          100% { box-shadow: 0 0 0 0 rgba(0, 229, 255, 0); }
        }
        .agent-pulse { animation: agentPulse 2s infinite; }
        .feed-row { animation: feedRowIn 0.3s ease both; }
        @keyframes feedRowIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
      `}} />
    </>
  );
}
