// Human-readable formatters for user-facing text. The backend and the place
// providers hand us raw tokens (ISO dates, English category slugs, internal
// status keys); everything the user actually reads should pass through here so
// the UI stays in pt-BR and never leaks a variable name.

// "2026-06-07" → "07/06/2026". Parses the y-m-d parts by hand instead of
// `new Date(iso)` so a UTC-midnight string doesn't shift a day in a negative
// timezone (Brazil is UTC-3). Anything that isn't a plain ISO date is returned
// untouched so we never render "Invalid Date".
export function formatDateBR(value?: string | null): string {
  if (!value) return "";
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!match) return value;
  const [, year, month, day] = match;
  return `${day}/${month}/${year}`;
}

// "07/06/2026 — 12/06/2026", skipping the dash when one end is missing.
export function formatDateRangeBR(start?: string | null, end?: string | null): string {
  const from = formatDateBR(start);
  const to = formatDateBR(end);
  if (from && to) return `${from} — ${to}`;
  return from || to;
}

// Friendly pt-BR labels for the place "kind"/"category" tokens the agent and
// the providers emit. Known keys are translated; anything unmapped is
// prettified (slug separators → spaces, Title Case) so even an unexpected value
// reads like a label instead of "point_of_interest".
const KIND_LABELS: Record<string, string> = {
  restaurant: "Restaurante",
  food: "Restaurante",
  cafe: "Café",
  bar: "Bar",
  museum: "Museu",
  attraction: "Atração",
  landmark: "Ponto turístico",
  point_of_interest: "Ponto turístico",
  tourist_attraction: "Ponto turístico",
  park: "Parque",
  beach: "Praia",
  viewpoint: "Mirante",
  nightlife: "Vida noturna",
  shopping: "Compras",
  hotel: "Hospedagem",
  accommodation: "Hospedagem",
  culture: "Cultura",
  outdoor: "Ar livre",
};

export function kindLabel(value?: string | null): string {
  if (!value) return "";
  const key = value.trim().toLowerCase().replace(/[\s-]+/g, "_");
  if (KIND_LABELS[key]) return KIND_LABELS[key];
  return value
    .trim()
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

// Trip lifecycle status → pt-BR.
const TRIP_STATUS_LABELS: Record<string, string> = {
  draft: "Rascunho",
  planned: "Planejado",
  planning: "Planejando",
  ready: "Pronto",
  completed: "Concluída",
  archived: "Arquivada",
  cancelled: "Cancelada",
};

export function tripStatusLabel(value?: string | null): string {
  if (!value) return "";
  return TRIP_STATUS_LABELS[value.trim().toLowerCase()] ?? kindLabel(value);
}

// Itinerary-version status → pt-BR.
const VERSION_STATUS_LABELS: Record<string, string> = {
  active: "ativa",
  archived: "arquivada",
  superseded: "substituída",
  draft: "rascunho",
};

export function versionStatusLabel(value?: string | null): string {
  if (!value) return "";
  return VERSION_STATUS_LABELS[value.trim().toLowerCase()] ?? value;
}

// The agent's internal tool names (update_item, set_day, search_places…) leak
// into the chat log as raw snake_case. Map them to plain-language pt-BR labels
// the traveler understands; unknown names fall back to a prettified slug.
const TOOL_LABELS: Record<string, string> = {
  search_places: "Buscando lugares",
  list_saved_places: "Consultando lugares salvos",
  list_current_options: "Revisando opções",
  start_itinerary: "Montando roteiro",
  finalize_itinerary: "Finalizando roteiro",
  review_itinerary: "Revisando roteiro",
  insert_item: "Adicionando atividade",
  place_item: "Adicionando atividade",
  update_item: "Atualizando atividade",
  remove_item: "Removendo atividade",
  set_day: "Reorganizando o dia",
  get_day_schedule: "Consultando a agenda do dia",
  get_day_context: "Analisando o dia",
  get_trip_snapshot: "Consultando a viagem",
  get_weather_forecast: "Verificando o clima",
  check_route: "Verificando trajetos",
  estimate_route: "Calculando deslocamentos",
  rollback_version: "Restaurando versão anterior",
  finish: "Concluindo",
};

export function toolLabel(value?: string | null): string {
  if (!value) return "";
  return TOOL_LABELS[value.trim().toLowerCase()] ?? kindLabel(value);
}
