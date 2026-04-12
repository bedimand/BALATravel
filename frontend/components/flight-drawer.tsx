import type { FlightOption } from "@/lib/types";

type Props = {
  flights: FlightOption[];
  selectedFlightId?: number | null;
  selectingId?: number | null;
  onSelectFlight?: (flightId: number) => Promise<void>;
  disabled?: boolean;
};

export function FlightDrawer({ flights, selectedFlightId, selectingId, onSelectFlight, disabled = false }: Props) {
  return (
    <section className={`panel decision-panel ${disabled && !selectedFlightId ? "decision-panel--disabled" : ""}`}>
      <div className="decision-panel__header">
        <div>
          <p className="eyebrow">Etapa 1</p>
          <h2>Escolher voo</h2>
        </div>
        <span>{flights.length} opcoes</span>
      </div>
      <p className="decision-panel__lede">
        O agente pode comparar trade-offs, mas a aprovacao final do voo precisa ser sua.
      </p>
      {!flights.length ? (
        <div className="empty-state">
          <strong>Nenhum voo carregado</strong>
          <p>Atualize as opcoes para comparar alternativas antes de seguir para a hospedagem.</p>
        </div>
      ) : (
        <div className="decision-list">
          {flights.map((flight) => (
            <article key={flight.id} className={`decision-item ${flight.id === selectedFlightId ? "decision-item--selected" : ""}`}>
              <div className="decision-item__body">
                <strong>
                  {flight.currency} {flight.price}
                </strong>
                <span>{flight.legs_json[0]?.departure_airport} → {flight.legs_json[0]?.arrival_airport}</span>
                <p>{flight.baggage_summary}</p>
              </div>
              <div className="decision-item__actions">
                <a href={flight.deeplink} target="_blank" rel="noreferrer">
                  Abrir oferta
                </a>
                {onSelectFlight ? (
                  <button
                    className={flight.id === selectedFlightId ? "button-primary" : "button-secondary"}
                    disabled={disabled || selectingId === flight.id}
                    onClick={async () => {
                      await onSelectFlight(flight.id);
                    }}
                    type="button"
                  >
                    {selectingId === flight.id ? "Salvando..." : flight.id === selectedFlightId ? "Selecionado" : "Escolher"}
                  </button>
                ) : null}
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
