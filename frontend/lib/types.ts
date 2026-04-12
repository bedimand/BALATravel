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

export type WorkflowStage = "planning" | "approved" | "booked";

export type WorkflowResponse = {
  stage: WorkflowStage;
  stage_status: "idle" | "running" | "completed" | "failed";
  step: number;
  total_steps: number;
};

export type DecisionOption = {
  id: string;
  label: string;
};

export type Decision = {
  id: number;
  decision_type: string;
  title: string;
  summary: string;
  options_json: DecisionOption[];
  status: "pending" | "decided";
};

export type WorkspaceResponse = {
  trip: Trip;
  workflow: WorkflowResponse;
  map: MapResponse;
  decisions: Decision[];
  hotels: HotelOption[];
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

export type HotelOption = {
  id: number;
  name: string;
  address: string;
  lat: number;
  lng: number;
  description: string | null;
  rating: number | null;
  price_per_night: number | null;
  is_selected: boolean;
};

export type PlanResponse = {
  itinerary: ItineraryVersion;
  map: MapResponse;
};
