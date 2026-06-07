import type {
  AgentMessageResponse,
  AgentThread,
  AgentStatusResponse,
  BackgroundRunResponse,
  ChatResponse,
  ItineraryResponse,
  MapResponse,
  Place,
  ProposedChange,
  TodaySummary,
  Trip,
  UserProfile,
  WorkspaceResponse
} from "@/lib/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000/api";

type RequestOptions = {
  method?: string;
  body?: unknown;
};

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    method: options.method ?? "GET",
    headers: {
      "Content-Type": "application/json"
    },
    body: options.body ? JSON.stringify(options.body) : undefined,
    cache: "no-store"
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(payload.detail ?? "Request failed");
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export const api = {
  me: () => request<UserProfile>("/users/me"),
  createTrip: (body: Record<string, unknown>) => request<Trip>("/trips", { method: "POST", body }),
  listTrips: () => request<Trip[]>("/trips"),
  getTrip: (tripId: string | number) => request<Trip>(`/trips/${tripId}`),
  updateTrip: (tripId: string | number, body: Record<string, unknown>) =>
    request<Trip>(`/trips/${tripId}`, { method: "PATCH", body }),
  getTripPlaces: (tripId: string | number) => request<Place[]>(`/trips/${tripId}/places`),
  updatePlaceSelection: (tripId: string | number, placeId: string | number, body: { is_selected: boolean }) =>
    request<WorkspaceResponse>(`/trips/${tripId}/places/${placeId}`, { method: "PATCH", body }),
  generateItinerary: (tripId: string | number) =>
    request<BackgroundRunResponse>(`/trips/${tripId}/itinerary/generate`, { method: "POST" }),
  replanItinerary: (tripId: string | number) =>
    request<BackgroundRunResponse>(`/trips/${tripId}/itinerary/replan`, { method: "POST" }),
  chatTrip: (tripId: string | number, body: { message: string }) =>
    request<ChatResponse>(`/trips/${tripId}/chat`, { method: "POST", body }),
  applyChatChange: (tripId: string | number, change: ProposedChange) =>
    request<ItineraryResponse>(`/trips/${tripId}/chat/apply`, { method: "POST", body: { change } }),
  updateItem: (tripId: string | number, itemId: string | number, body: Record<string, unknown>) =>
    request(`/trips/${tripId}/itinerary/items/${itemId}`, { method: "PATCH", body }),
  getMap: (tripId: string | number) => request<MapResponse>(`/trips/${tripId}/map`),
  exportTrip: (tripId: string | number) =>
    request<{ export_id: number; file_url: string; format: string }>(`/trips/${tripId}/export`, { method: "POST" }),
  createShareLink: (tripId: string | number) =>
    request<{ token: string; public_url: string; expires_at: string }>(`/trips/${tripId}/share-links`, { method: "POST" }),
  sendAgentMessage: (tripId: string | number, body: { message: string }) =>
    request<BackgroundRunResponse>(`/trips/${tripId}/agent/messages`, { method: "POST", body }),
  getAgentThread: (tripId: string | number) => request<AgentThread>(`/trips/${tripId}/agent/thread`),
  rollbackAgentVersion: (tripId: string | number, versionId: string | number) =>
    request<AgentMessageResponse>(`/trips/${tripId}/agent/rollback/${versionId}`, { method: "POST" }),
  getWorkspace: (tripId: string | number) => request<WorkspaceResponse>(`/trips/${tripId}/workspace`),
  startWorkflow: (tripId: string | number, runType = "setup") =>
    request<BackgroundRunResponse>(`/trips/${tripId}/workflow/start`, { method: "POST", body: { run_type: runType } }),
  sendWorkflowMessage: (tripId: string | number, body: { message: string; scope?: string }) =>
    request<WorkspaceResponse>(`/trips/${tripId}/workflow/messages`, { method: "POST", body }),
  decideWorkflow: (
    tripId: string | number,
    decisionId: string | number,
    body: { action: "approve" | "reject" | "select"; selected_option_id?: string }
  ) => request<WorkspaceResponse>(`/trips/${tripId}/workflow/decisions/${decisionId}`, { method: "POST", body }),
  refreshWorkflow: (tripId: string | number) =>
    request<BackgroundRunResponse>(`/trips/${tripId}/workflow/refresh`, { method: "POST" }),
  replanDay: (tripId: string | number, body: { date: string; goal: string }) =>
    request<WorkspaceResponse>(`/trips/${tripId}/workflow/replan-day`, { method: "POST", body }),
  rebuildPlanFromSelection: (tripId: string | number) =>
    request<BackgroundRunResponse>(`/trips/${tripId}/workflow/rebuild-plan`, { method: "POST" }),
  getToday: (tripId: string | number) => request<TodaySummary | null>(`/trips/${tripId}/today`),
  getAgentStatus: (tripId: string | number) => request<AgentStatusResponse>(`/trips/${tripId}/agent-status`)
};
