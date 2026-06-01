"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import type { AgentThread } from "@/lib/types";

type Props = {
  tripId: string;
  summary: string;
  currentStep: string;
  onRunComplete: (assistantMessage: string, warnings: string[]) => Promise<void>;
};

const STEP_PROMPTS: Record<string, string[]> = {
  search: [
    "Busque boas opcoes de voo, hospedagem e atracoes para esta viagem.",
    "Que criterios devo usar para comparar bem as opcoes desta viagem?"
  ],
  flight: [
    "Compare os voos encontrados e destaque os melhores trade-offs para eu decidir.",
    "Quais voos parecem melhores para custo x conforto?"
  ],
  hotel: [
    "Compare as hospedagens encontradas e me diga os pros e contras de cada uma.",
    "Qual hotel parece melhor como base para essa viagem?"
  ],
  places: [
    "Revise as atracoes sugeridas e diga se falta algo importante para este perfil.",
    "Com base nas atracoes atuais, o roteiro ja pode ser gerado?"
  ],
  itinerary: [
    "Otimize este roteiro para reduzir deslocamento.",
    "Quais ajustes voce faria sem mudar o estilo da viagem?"
  ]
};

const STEP_TITLES: Record<string, string> = {
  search: "Buscar contexto",
  flight: "Escolher voo",
  hotel: "Escolher hospedagem",
  places: "Revisar atracoes",
  itinerary: "Refinar roteiro"
};

export function ChatPanel({ tripId, summary, currentStep, onRunComplete }: Props) {
  const [thread, setThread] = useState<AgentThread | null>(null);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const quickPrompts = useMemo(() => STEP_PROMPTS[currentStep] ?? STEP_PROMPTS.search, [currentStep]);

  async function refreshThread() {
    const nextThread = await api.getAgentThread(tripId);
    setThread(nextThread);
  }

  useEffect(() => {
    refreshThread().catch((requestError) => {
      setError(requestError instanceof Error ? requestError.message : "Falha ao carregar o agente.");
    });
  }, [tripId]);

  async function submitMessage(message: string) {
    setSending(true);
    setError(null);
    try {
      await api.sendAgentMessage(tripId, { message });
      setDraft("");
      await onRunComplete("", []);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Falha ao executar a solicitacao.");
    } finally {
      setSending(false);
    }
  }

  async function handleSend(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = draft.trim();
    if (!message) {
      return;
    }
    await submitMessage(message);
  }

  return (
    <section className="panel assistant-panel">
      <div className="assistant-panel__intro">
        <div>
          <p className="eyebrow">Agente</p>
          <h2>Assistente da etapa</h2>
        </div>
        <span className="assistant-panel__step">{STEP_TITLES[currentStep] ?? STEP_TITLES.search}</span>
      </div>

      <p className="assistant-panel__summary">
        {summary || "Use o agente para comparar opcoes, identificar trade-offs e preparar a proxima decisao sem pular etapas."}
      </p>

      <div className="assistant-panel__prompts">
        {quickPrompts.map((prompt) => (
          <button
            key={prompt}
            className="assistant-chip"
            disabled={sending}
            onClick={async () => {
              await submitMessage(prompt);
            }}
            type="button"
          >
            {prompt}
          </button>
        ))}
      </div>

      <div className="assistant-log">
        {thread?.runs.length ? (
          thread.runs
            .slice()
            .reverse()
            .map((run) => (
              <article key={run.id} className="assistant-log__entry">
                {run.user_message ? <div className="chat-bubble user">{run.user_message}</div> : null}
                <div className="chat-bubble assistant">{run.assistant_message}</div>
                {run.tool_calls.length ? (
                  <div className="assistant-log__tools">
                    {run.tool_calls.map((call) => (
                      <span key={call.id} className={`tool-pill tool-pill--${call.status}`}>
                        {call.tool_name}
                      </span>
                    ))}
                  </div>
                ) : null}
                {run.warnings.length ? (
                  <div className="warning-box">
                    {run.warnings.map((warning) => (
                      <p key={`${run.id}-${warning}`}>{warning}</p>
                    ))}
                  </div>
                ) : null}
              </article>
            ))
        ) : (
          <div className="chat-bubble assistant">Ainda nao ha execucoes do agente para esta viagem.</div>
        )}
      </div>

      <form className="chat-form" onSubmit={handleSend}>
        <textarea
          rows={4}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Pergunte ao agente como comparar opcoes, quais riscos existem ou o que ainda falta decidir."
        />
        <button className="button-primary" type="submit" disabled={sending}>
          {sending ? "Executando..." : "Perguntar ao agente"}
        </button>
      </form>

      {error ? <p className="error-text">{error}</p> : null}
    </section>
  );
}
