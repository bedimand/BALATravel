export type Trip = {
  id: number;
  destination: string;
  start_date: string;
  end_date: string;
  budget: number;
  currency: string;
  interests: string[];
  travel_pace: string;
  traveler_sex: string;
  age_range: string;
  dietary_restrictions: string[];
  mobility_notes: string;
  has_car: boolean;
  accommodation_name: string | null;
  accommodation_address: string | null;
  accommodation_lat: number | null;
  accommodation_lng: number | null;
  daily_start_time: string;
  daily_end_time: string;
  status: string;
};

export type ItineraryItem = {
  id: number;
  date: string;
  start_time: string;
  end_time: string;
  item_type: string;
  title: string;
  place_ref: string | null;
  lat: number | null;
  lng: number | null;
  travel_time_min: number;
  travel_distance_km: number;
  notes: string | null;
  curator_reasoning: string | null;
};

export type ItineraryVersion = {
  id: number;
  trip_id: number;
  version: number;
  status: string;
  total_estimated_cost: number;
  assistant_summary: string;
  warnings: string[];
  items: ItineraryItem[];
};

export type WorkflowResponse = {
  current_stage: string;
  stage_status: string;
  active_workflow_run_id: number | null;
  last_user_goal: string | null;
};

export type DecisionOption = {
  id: string;
  label: string;
};

export type Decision = {
  id: number;
  decision_type: string;
  kind?: string;
  title: string;
  summary: string;
  options_json: DecisionOption[];
  recommended_option_id?: string | null;
  payload_json?: { proposal?: ProposedChange } & Record<string, unknown>;
  status: "pending" | "decided";
};

export type WorkspaceResponse = {
  trip: Trip;
  workflow: WorkflowResponse;
  workflow_runs: WorkflowRun[];
  map: MapResponse;
  decisions: Decision[];
  itinerary_versions: ItineraryVersion[];
};

export type MapResponse = {
  trip_id: number;
  markers: Array<{
    id: string;
    title: string;
    kind: string;
    lat: number;
    lng: number;
    date?: string | null;
    start_time?: string | null;
    summary?: string | null;
    image_url?: string | null;
    rating?: number | null;
    user_ratings_total?: number | null;
    address_full?: string | null;
    editorial_note?: string | null;
    price_level?: number | null;
    website?: string | null;
    curator_reasoning?: string | null;
  }>;
  routes: Array<{
    from_marker_id: string;
    to_marker_id: string;
    distance_km: number;
    duration_min: number;
    source: string;
    geometry: {
      type: "LineString";
      coordinates: number[][];
    };
  }>;
};

export type PlanResponse = {
  itinerary: ItineraryVersion;
  map: MapResponse;
};

export type BackgroundRunResponse = {
  run_id: number;
  status: string;
  message: string;
};

export type WorkflowRun = {
  id: number;
  run_type: string;
  status: string;
  started_at: string;
  completed_at: string | null;
};

export type AgentStep = {
  step_key: string;
  status: string;
  summary: string;
  reasoning: string | null;
  duration_ms: number | null;
};

export type AgentStatusResponse = {
  run_id: number;
  status: string;
  current_step_key: string | null;
  current_step_summary: string | null;
  progress_percent: number;
  steps: AgentStep[];
};

export type AgentMessageResponse = {
  run_id: number;
  assistant_message: string;
  warnings: string[];
  applied_changes: Record<string, unknown>[];
  proposed_followups: string[];
  itinerary_version_id: number | null;
  trip_snapshot: Record<string, unknown>;
};

export type AgentToolCall = {
  id: number;
  tool_name: string;
  status: string;
};

export type AgentRunEntry = {
  id: number;
  user_message: string | null;
  assistant_message: string | null;
  tool_calls: AgentToolCall[];
  warnings: string[];
};

export type AgentThread = {
  trip_id: number;
  runs: AgentRunEntry[];
  mutations: Record<string, unknown>[];
};

export type TodaySummary = {
  date: string;
  headline: string;
  quick_actions: string[];
  item_ids: number[];
  route_burden_min: number;
};

export type Place = {
  id: number;
  name: string;
  category: string;
  lat: number;
  lng: number;
  rating: number;
  is_selected: boolean;
  summary: string | null;
  image_url: string | null;
  deeplink?: string;
};

export type ItineraryResponse = {
  itinerary: ItineraryVersion;
  warnings: string[];
  assistant_summary: string;
};

export type UserProfile = {
  id: number;
  name: string;
  email: string;
  locale: string;
  currency: string;
};

export type ChatResponse = {
  message: string;
  proposed_changes: ProposedChange[];
};

export type ProposedChange = {
  type: string;
  title: string;
  reason: string;
  payload: Record<string, unknown>;
};
