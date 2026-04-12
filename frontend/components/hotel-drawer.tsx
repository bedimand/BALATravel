import type { HotelOption } from "@/lib/types";

type Props = {
  hotels: HotelOption[];
  selectedHotelId?: number | null;
  selectingId?: number | null;
  onSelectHotel?: (hotelId: number) => Promise<void>;
  disabled?: boolean;
};

export function HotelDrawer({ hotels, selectedHotelId, selectingId, onSelectHotel, disabled = false }: Props) {
  return (
    <section className={`panel decision-panel ${disabled && !selectedHotelId ? "decision-panel--disabled" : ""}`}>
      <div className="decision-panel__header">
        <div>
          <p className="eyebrow">Etapa 2</p>
          <h2>Escolher hospedagem</h2>
        </div>
        <span>{hotels.length} opcoes</span>
      </div>
      <p className="decision-panel__lede">
        Escolha a base da viagem depois do voo. O roteiro usa essa hospedagem como ancora do mapa e dos deslocamentos.
      </p>
      {!hotels.length ? (
        <div className="empty-state">
          <strong>Nenhuma hospedagem carregada</strong>
          <p>Atualize a busca para comparar opcoes antes de montar a agenda.</p>
        </div>
      ) : (
        <div className="decision-list">
          {hotels.map((hotel) => (
            <article key={hotel.id} className={`decision-item ${hotel.id === selectedHotelId ? "decision-item--selected" : ""}`}>
              <div className="decision-item__body">
                <strong>{hotel.name}</strong>
                <span>
                  Nota {hotel.rating} • total {hotel.total_price}
                </span>
                <p>Base sugerida para explorar {hotel.lat.toFixed(3)}, {hotel.lng.toFixed(3)}.</p>
              </div>
              <div className="decision-item__actions">
                <a href={hotel.deeplink} target="_blank" rel="noreferrer">
                  Ver detalhes
                </a>
                {onSelectHotel ? (
                  <button
                    className={hotel.id === selectedHotelId ? "button-primary" : "button-secondary"}
                    disabled={disabled || selectingId === hotel.id}
                    onClick={async () => {
                      await onSelectHotel(hotel.id);
                    }}
                    type="button"
                  >
                    {selectingId === hotel.id ? "Salvando..." : hotel.id === selectedHotelId ? "Selecionado" : "Escolher"}
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
