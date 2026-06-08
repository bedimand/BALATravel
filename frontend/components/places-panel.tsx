import { kindLabel } from "@/lib/format";
import type { Place } from "@/lib/types";

type Props = {
  places: Place[];
  enabled: boolean;
};

export function PlacesPanel({ places, enabled }: Props) {
  return (
    <section className={`panel decision-panel ${enabled ? "" : "decision-panel--disabled"}`}>
      <div className="decision-panel__header">
        <div>
          <p className="eyebrow">Etapa 3</p>
          <h2>Revisar atracoes</h2>
        </div>
        <span>{places.length} sugestoes</span>
      </div>
      <p className="decision-panel__lede">
        {enabled
          ? "Use o agente para validar se as atracoes estao coerentes com o estilo da viagem antes de montar a agenda."
          : "A etapa de atracoes fica liberada depois que voo e hospedagem forem escolhidos."}
      </p>
      {places.length ? (
        <div className="decision-list">
          {places.slice(0, 8).map((place) => (
            <article key={place.id} className="decision-item">
              <div className="decision-item__body">
                <strong>{place.name}</strong>
                <span>
                  {kindLabel(place.category)} - nota {place.rating}
                </span>
                <p>{place.summary || "Sem resumo adicional."}</p>
              </div>
              <a href={place.deeplink} target="_blank" rel="noreferrer">
                Abrir
              </a>
            </article>
          ))}
        </div>
      ) : (
        <div className="empty-state">
          <strong>Nenhuma atracao carregada</strong>
          <p>Busque opcoes para receber sugestoes de lugares antes de gerar a agenda.</p>
        </div>
      )}
    </section>
  );
}
