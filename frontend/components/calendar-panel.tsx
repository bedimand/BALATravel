"use client";

import { FormEvent, useState } from "react";

import { api } from "@/lib/api";
import type { ItineraryItem, ItineraryVersion } from "@/lib/types";

type Props = {
  tripId: string;
  itinerary: ItineraryVersion | null;
  onItemSaved: () => Promise<void>;
};

function groupByDate(items: ItineraryItem[]) {
  return items.reduce<Record<string, ItineraryItem[]>>((accumulator, item) => {
    accumulator[item.date] = [...(accumulator[item.date] ?? []), item];
    return accumulator;
  }, {});
}

export function CalendarPanel({ tripId, itinerary, onItemSaved }: Props) {
  const [savingId, setSavingId] = useState<number | null>(null);

  if (!itinerary) {
    return (
      <section className="panel result-panel">
        <div className="section-header">
          <h2>Agenda</h2>
          <span>Aguardando geracao</span>
        </div>
        <div className="empty-state">
          <strong>A agenda aparece aqui no fim do fluxo</strong>
          <p>Depois de escolher voo e hospedagem e revisar as atracoes, gere o roteiro para editar os blocos do dia.</p>
        </div>
      </section>
    );
  }

  const grouped = groupByDate(itinerary.items);

  async function handleSave(item: ItineraryItem, event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    setSavingId(item.id);
    await api.updateItem(tripId, item.id, {
      title: String(formData.get("title")),
      notes: String(formData.get("notes")),
      start_time: String(formData.get("start_time")),
      end_time: String(formData.get("end_time"))
    });
    setSavingId(null);
    await onItemSaved();
  }

  return (
    <section className="panel result-panel stack-gap">
      <div className="section-header">
        <h2>Agenda diaria</h2>
        <span>Custo estimado {itinerary.total_estimated_cost}</span>
      </div>
      {Object.entries(grouped).map(([date, items]) => (
        <div key={date} className="day-column">
          <header>
            <strong>{date}</strong>
          </header>
          {items.map((item) => (
            <form
              key={item.id}
              className="itinerary-card"
              onSubmit={async (event) => {
                await handleSave(item, event);
              }}
            >
              <input name="title" defaultValue={item.title} />
              <div className="time-grid">
                <input name="start_time" defaultValue={item.start_time} />
                <input name="end_time" defaultValue={item.end_time} />
              </div>
              <textarea name="notes" defaultValue={item.notes ?? ""} rows={3} />
              <div className="card-footer">
                <span>{item.travel_time_min} min de deslocamento</span>
                <button className="button-secondary" type="submit" disabled={savingId === item.id}>
                  {savingId === item.id ? "Salvando..." : "Salvar"}
                </button>
              </div>
            </form>
          ))}
        </div>
      ))}
    </section>
  );
}
