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
  TokenPair,
  Trip,
  UserProfile,
  WorkspaceResponse
} from "@/lib/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000/api";

const ACCESS_TOKEN_KEY = "bala_access";
const REFRESH_TOKEN_KEY = "bala_refresh";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(ACCESS_TOKEN_KEY);
}

function setTokens(access: string, refresh: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(ACCESS_TOKEN_KEY, access);
  window.localStorage.setItem(REFRESH_TOKEN_KEY, refresh);
}

function clearTokens(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(ACCESS_TOKEN_KEY);
  window.localStorage.removeItem(REFRESH_TOKEN_KEY);
}

type RequestOptions = {
  method?: string;
  body?: unknown;
};

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const token = getToken();
  const response = await fetch(`${API_URL}${path}`, {
    method: options.method ?? "GET",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    },
    body: options.body ? JSON.stringify(options.body) : undefined,
    cache: "no-store"
  });

  if (response.status === 401) {
    clearTokens();
    if (typeof window !== "undefined" && window.location.pathname !== "/login") {
      window.location.href = "/login";
    }
    throw new Error("Sessao expirada. Faca login novamente.");
  }

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
  signup: async (body: { name: string; email: string; password: string }) => {
    const tokens = await request<TokenPair>("/auth/signup", { method: "POST", body });
    setTokens(tokens.access_token, tokens.refresh_token);
    return tokens;
  },
  login: async (body: { email: string; password: string }) => {
    const tokens = await request<TokenPair>("/auth/login", { method: "POST", body });
    setTokens(tokens.access_token, tokens.refresh_token);
    return tokens;
  },
  logout: () => {
    clearTokens();
    if (typeof window !== "undefined") {
      window.location.href = "/login";
    }
  },
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
