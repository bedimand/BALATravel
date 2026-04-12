"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { AgentStatusResponse } from "@/lib/types";

export function AgentThinking({ tripId, onComplete }: { tripId: number; onComplete: () => void }) {
  const [status, setStatus] = useState<AgentStatusResponse | null>(null);

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

  return (
    <div className="agent-thinking-screen" style={{
      position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
      background: "var(--bg)", 
      zIndex: 9999,
      display: "flex", 
      alignItems: "center",
      justifyContent: "center",
      padding: "2rem",
      backdropFilter: "blur(10px)",
      WebkitBackdropFilter: "blur(10px)"
    }}>
      <div style={{
        width: "100%",
        maxWidth: "400px",
        background: "var(--surface-strong)",
        border: "1px solid var(--line-strong)",
        borderRadius: "var(--radius-card)",
        padding: "2.5rem",
        boxShadow: "var(--shadow)",
        display: "flex",
        flexDirection: "column",
        gap: "1.5rem",
        textAlign: "center"
      }}>
        <div style={{ display: "flex", justifyContent: "center" }}>
          <div className="map-pin" style={{ 
            width: "3.5rem", height: "3.5rem", 
            background: "var(--primary-soft)",
            display: "flex", alignItems: "center", justifyContent: "center",
            borderRadius: "50%",
            animation: "pulse-glow 2s infinite"
          }}>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--primary)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 22s-8-4.5-8-11.8A8 8 0 0 1 12 2a8 8 0 0 1 8 8.2c0 7.3-8 11.8-8 11.8z" />
              <circle cx="12" cy="10" r="3" />
            </svg>
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
          <h2 style={{ fontSize: "1.4rem", margin: 0, fontFamily: "var(--font-display)" }}>
            Planejamento em Curso
          </h2>
          <p style={{ color: "var(--muted)", fontSize: "0.9rem", margin: 0 }}>
            Seu Agente de Viagem está configurando o roteiro perfeito.
          </p>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem", textAlign: "left" }}>
          {status?.steps.slice(-3).map((step, idx, arr) => (
            <div key={`${step.step_key}-${idx}`} style={{
              padding: "0.85rem 1rem",
              borderRadius: "12px",
              background: idx === arr.length - 1 ? "var(--primary-soft)" : "var(--surface)",
              border: "1px solid",
              borderColor: idx === arr.length - 1 ? "var(--primary-soft)" : "var(--line)",
              display: "flex",
              alignItems: "center",
              gap: "0.75rem",
              transition: "all 0.4s ease"
            }}>
               <div style={{ 
                 width: "8px", height: "8px", borderRadius: "50%", 
                 background: step.status === "completed" ? "var(--primary)" : (step.status === "failed" ? "var(--danger)" : "var(--warning)"),
                 boxShadow: step.status === "running" ? "0 0 10px var(--warning)" : "none",
                 marginTop: "0.25rem"
               }} />
               <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "0.2rem" }}>
                 <span style={{ fontSize: "0.85rem", fontWeight: 500 }}>
                   {step.summary}
                 </span>
                 {step.reasoning && (
                   <span style={{ fontSize: "0.75rem", opacity: 0.6, fontStyle: "italic", lineHeight: 1.3 }}>
                     {step.reasoning}
                   </span>
                 )}
               </div>
            </div>
          ))}
          {!status?.steps.length && (
            <div style={{ textAlign: "center", padding: "1rem", opacity: 0.5, fontSize: "0.85rem" }}>
              Iniciando camada de inteligência...
            </div>
          )}
        </div>

        {status?.status === "running" && (
          <div style={{ marginTop: "0.5rem" }}>
            <div style={{ width: "100%", height: "4px", background: "var(--line)", borderRadius: "2px", overflow: "hidden" }}>
              <div style={{ 
                width: `${status.progress_percent}%`, 
                height: "100%", 
                background: "linear-gradient(90deg, var(--primary), var(--accent))", 
                transition: "width 1s cubic-bezier(0.4, 0, 0.2, 1)" 
              }} />
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: "0.5rem", fontSize: "0.75rem", color: "var(--muted)" }}>
              <span>Modo CentralAgent</span>
              <span>{Math.round(status.progress_percent)}%</span>
            </div>
          </div>
        )}
      </div>

      <style dangerouslySetInnerHTML={{__html: `
        @keyframes pulse-glow {
          0% { box-shadow: 0 0 0 0 rgba(0, 229, 255, 0.4); transform: scale(1); }
          70% { box-shadow: 0 0 0 15px rgba(0, 229, 255, 0); transform: scale(1.05); }
          100% { box-shadow: 0 0 0 0 rgba(0, 229, 255, 0); transform: scale(1); }
        }
      `}} />
    </div>
  );
}
