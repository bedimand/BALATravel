from __future__ import annotations

from datetime import date as dt_date
from datetime import datetime as dt_datetime
from datetime import time as dt_time
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator


class TripCreate(BaseModel):
    destination: str = Field(min_length=2, max_length=120)
    origin_city: str | None = Field(default=None, min_length=2, max_length=120)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    locale: str | None = Field(default=None, min_length=2, max_length=10)
    start_date: dt_date
    end_date: dt_date
    budget: Decimal = Field(gt=0)
    style: str = Field(min_length=2, max_length=50)
    interests: list[str] = Field(default_factory=list)
    accommodation_name: str | None = None
    accommodation_address: str | None = None
    accommodation_lat: float | None = None
    accommodation_lng: float | None = None
    age_range: str | None = None
    traveler_sex: str | None = None
    travel_pace: str | None = None
    dietary_restrictions: list[str] = Field(default_factory=list)
    mobility_notes: str | None = None
    languages: list[str] = Field(default_factory=list)
    has_car: bool = False
    daily_start_time: dt_time = dt_time(9, 0)
    daily_end_time: dt_time = dt_time(22, 0)

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip().upper()
        return text or None

    @field_validator("origin_city", mode="before")
    @classmethod
    def normalize_origin_city(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("locale", mode="before")
    @classmethod
    def normalize_locale(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


class TripUpdate(BaseModel):
    destination: str | None = Field(default=None, min_length=2, max_length=120)
    origin_city: str | None = Field(default=None, min_length=2, max_length=120)
    selected_flight_id: int | None = None
    selected_hotel_id: int | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    locale: str | None = Field(default=None, min_length=2, max_length=10)
    start_date: dt_date | None = None
    end_date: dt_date | None = None
    budget: Decimal | None = Field(default=None, gt=0)
    style: str | None = Field(default=None, min_length=2, max_length=50)
    interests: list[str] | None = None
    status: str | None = None
    has_car: bool | None = None
    daily_start_time: dt_time | None = None
    daily_end_time: dt_time | None = None

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_update_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip().upper()
        return text or None

    @field_validator("origin_city", mode="before")
    @classmethod
    def normalize_update_origin_city(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("locale", mode="before")
    @classmethod
    def normalize_update_locale(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


class FlightOptionRead(BaseModel):
    id: int
    provider_ref: str
    price: Decimal
    currency: str
    legs_json: list[dict[str, Any]]
    baggage_summary: str
    deeplink: str
    source: str
    confidence: float
    fetched_at: dt_datetime

    model_config = {"from_attributes": True}


class HotelOptionRead(BaseModel):
    id: int
    provider_ref: str
    name: str
    nightly_price: Decimal
    total_price: Decimal
    rating: float
    lat: float
    lng: float
    deeplink: str
    source: str
    confidence: float
    fetched_at: dt_datetime

    model_config = {"from_attributes": True}


class PlaceRead(BaseModel):
    id: int
    external_id: str
    name: str
    category: str
    lat: float
    lng: float
    opening_hours_json: dict[str, Any]
    rating: float
    estimated_duration: int
    is_selected: bool
    hours_confidence: float
    source: str
    confidence: float
    fetched_at: dt_datetime
    summary: str | None = None
    image_url: str | None = None
    deeplink: str
    photos_json: list[str] = Field(default_factory=list)
    price_level: int | None = None
    user_ratings_total: int | None = None
    website: str | None = None
    phone: str | None = None
    address_full: str | None = None
    google_place_id: str | None = None
    editorial_note: str | None = None
    neighborhood: str | None = None
    interest_tags: list[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ItineraryItemRead(BaseModel):
    id: int
    date: dt_date
    start_time: dt_time
    end_time: dt_time
    item_type: str
    title: str
    place_ref: str | None = None
    lat: float | None = None
    lng: float | None = None
    travel_time_min: int
    travel_distance_km: float = 0.0
    notes: str | None = None

    model_config = {"from_attributes": True}


class ItineraryVersionRead(BaseModel):
    id: int
    version: int
    status: str
    total_estimated_cost: Decimal
    assistant_summary: str
    warnings: list[str]
    generated_at: dt_datetime
    items: list[ItineraryItemRead]

    model_config = {"from_attributes": True}


class TripRead(BaseModel):
    id: int
    destination: str
    origin_city: str | None = None
    selected_flight_id: int | None = None
    selected_hotel_id: int | None = None
    currency: str
    locale: str
    start_date: dt_date
    end_date: dt_date
    budget: Decimal
    style: str
    interests: list[str]
    status: str
    created_at: dt_datetime
    accommodation_name: str | None = None
    accommodation_address: str | None = None
    accommodation_lat: float | None = None
    accommodation_lng: float | None = None
    age_range: str | None = None
    traveler_sex: str | None = None
    travel_pace: str | None = None
    dietary_restrictions: list[str] = Field(default_factory=list)
    mobility_notes: str | None = None
    languages: list[str] = Field(default_factory=list)
    has_car: bool = False
    daily_start_time: dt_time = dt_time(9, 0)
    daily_end_time: dt_time = dt_time(22, 0)
    flights: list[FlightOptionRead] = Field(default_factory=list)
    hotels: list[HotelOptionRead] = Field(default_factory=list)
    itinerary_versions: list[ItineraryVersionRead] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class SearchResponse(BaseModel):
    trip_id: int
    destination: str
    flights: list[FlightOptionRead]
    hotels: list[HotelOptionRead]
    places: list[PlaceRead]
    warnings: list[str] = Field(default_factory=list)


class ItineraryResponse(BaseModel):
    itinerary: ItineraryVersionRead
    warnings: list[str] = Field(default_factory=list)
    assistant_summary: str


class ProposedChange(BaseModel):
    type: str
    title: str
    reason: str
    payload: dict[str, Any] = Field(default_factory=dict)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1200)


class ChatResponse(BaseModel):
    assistant_message: str
    proposed_changes: list[ProposedChange] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ChatApplyRequest(BaseModel):
    change: ProposedChange


class ItineraryItemUpdate(BaseModel):
    start_time: dt_time | None = None
    end_time: dt_time | None = None
    title: str | None = Field(default=None, min_length=2, max_length=120)
    notes: str | None = Field(default=None, max_length=500)


class MapMarker(BaseModel):
    id: str
    title: str
    kind: str
    lat: float
    lng: float
    date: dt_date | None = None
    start_time: dt_time | None = None
    summary: str | None = None
    image_url: str | None = None
    rating: float | None = None
    user_ratings_total: int | None = None
    address_full: str | None = None
    editorial_note: str | None = None
    price_level: int | None = None
    website: str | None = None
    curator_reasoning: str | None = None


class MapGeometry(BaseModel):
    type: str
    coordinates: list[list[float]] = Field(default_factory=list)


class MapRoute(BaseModel):
    from_marker_id: str
    to_marker_id: str
    distance_km: float = 0.0
    duration_min: int = 0
    source: str = "unavailable"
    geometry: MapGeometry


class MapResponse(BaseModel):
    trip_id: int
    markers: list[MapMarker]
    routes: list[MapRoute]


class PlaceSelectionUpdate(BaseModel):
    is_selected: bool


class ExportResponse(BaseModel):
    export_id: int
    file_url: str
    format: str


class ShareLinkResponse(BaseModel):
    token: str
    public_url: str
    expires_at: dt_datetime


class PublicTripResponse(BaseModel):
    destination: str
    start_date: dt_date
    end_date: dt_date
    itinerary: ItineraryVersionRead | None = None
    hotels: list[HotelOptionRead] = Field(default_factory=list)


class AgentMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class AgentToolCallRead(BaseModel):
    id: int
    tool_name: str
    arguments_json: dict[str, Any]
    result_json: dict[str, Any]
    status: str
    started_at: dt_datetime
    completed_at: dt_datetime | None = None

    model_config = {"from_attributes": True}


class AgentRunRead(BaseModel):
    id: int
    intent: str
    status: str
    user_message: str | None = None
    assistant_message: str
    warnings: list[str]
    applied_changes: list[dict[str, Any]]
    model: str
    prompt_version: str
    created_at: dt_datetime
    completed_at: dt_datetime | None = None
    tool_calls: list[AgentToolCallRead] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class PlanMutationRead(BaseModel):
    id: int
    mutation_type: str
    rationale: str
    changed_item_ids: list[int]
    from_itinerary_version_id: int | None = None
    to_itinerary_version_id: int | None = None
    created_at: dt_datetime

    model_config = {"from_attributes": True}


class AgentMessageResponse(BaseModel):
    run_id: int
    assistant_message: str
    warnings: list[str] = Field(default_factory=list)
    applied_changes: list[dict[str, Any]] = Field(default_factory=list)
    proposed_followups: list[str] = Field(default_factory=list)
    itinerary_version_id: int | None = None
    trip_snapshot: dict[str, Any]


class AgentThreadResponse(BaseModel):
    trip_id: int
    runs: list[AgentRunRead] = Field(default_factory=list)
    mutations: list[PlanMutationRead] = Field(default_factory=list)


class WorkflowStateRead(BaseModel):
    id: int
    current_stage: str
    stage_status: str
    active_workflow_run_id: int | None = None
    last_user_goal: str | None = None
    last_synced_at: dt_datetime | None = None

    model_config = {"from_attributes": True}


class WorkflowRunRead(BaseModel):
    id: int
    run_type: str
    status: str
    started_at: dt_datetime
    completed_at: dt_datetime | None = None

    model_config = {"from_attributes": True}


class WorkflowStepRead(BaseModel):
    id: int
    step_key: str
    status: str
    summary: str
    reasoning: str | None = None
    input_json: dict[str, Any]
    output_json: dict[str, Any]
    started_at: dt_datetime
    completed_at: dt_datetime | None = None

    model_config = {"from_attributes": True}


class DecisionRequestRead(BaseModel):
    id: int
    kind: str
    status: str
    title: str
    summary: str
    options_json: list[dict[str, Any]] = Field(default_factory=list)
    recommended_option_id: str | None = None
    selected_option_id: str | None = None
    payload_json: dict[str, Any] = Field(default_factory=dict)
    created_at: dt_datetime
    decided_at: dt_datetime | None = None

    model_config = {"from_attributes": True}


class AgentArtifactRead(BaseModel):
    id: int
    artifact_type: str
    title: str
    summary: str
    payload_json: dict[str, Any] = Field(default_factory=dict)
    created_at: dt_datetime

    model_config = {"from_attributes": True}


class TripWeatherSnapshotRead(BaseModel):
    id: int
    forecast_date: dt_date
    condition_label: str
    temp_min_c: float | None = None
    temp_max_c: float | None = None
    rain_probability: float
    is_outdoor_risky: bool
    source: str
    fetched_at: dt_datetime

    model_config = {"from_attributes": True}


class RouteSummaryRead(BaseModel):
    travel_mode: str
    total_travel_min: int
    total_distance_km: float
    average_leg_min: int
    average_leg_km: float
    max_leg_min: int
    max_leg_km: float
    source: str


class TodaySummaryRead(BaseModel):
    date: dt_date
    headline: str
    quick_actions: list[str] = Field(default_factory=list)
    item_ids: list[int] = Field(default_factory=list)
    route_burden_min: int = 0
    weather: TripWeatherSnapshotRead | None = None


class WorkspaceResponse(BaseModel):
    trip: TripRead
    workflow: WorkflowStateRead
    workflow_runs: list[WorkflowRunRead] = Field(default_factory=list)
    decisions: list[DecisionRequestRead] = Field(default_factory=list)
    artifacts: list[AgentArtifactRead] = Field(default_factory=list)
    active_itinerary: ItineraryVersionRead | None = None
    version_history: list[ItineraryVersionRead] = Field(default_factory=list)
    map: MapResponse
    today: TodaySummaryRead | None = None
    weather: list[TripWeatherSnapshotRead] = Field(default_factory=list)
    route_summary: RouteSummaryRead


class WorkflowStartRequest(BaseModel):
    run_type: str = Field(default="setup", min_length=2, max_length=40)


class WorkflowMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    scope: str = Field(default="trip", min_length=2, max_length=40)


class WorkflowDecisionRequest(BaseModel):
    action: str = Field(pattern="^(approve|reject|select)$")
    selected_option_id: str | None = None


class ReplanDayRequest(BaseModel):
    date: dt_date
    goal: str = Field(min_length=3, max_length=400)


class AgentStepRead(BaseModel):
    step_key: str
    status: str
    summary: str
    reasoning: str | None = None
    duration_ms: int | None = None


class AgentStatusResponse(BaseModel):
    run_id: int
    status: str
    current_step_key: str | None = None
    current_step_summary: str | None = None
    progress_percent: int = 0
    steps: list[AgentStepRead] = Field(default_factory=list)


class BackgroundRunResponse(BaseModel):
    run_id: int
    status: str = "running"
    message: str = "Processing started. Poll /agent-status for progress."


ItineraryItemRead.model_rebuild()
ItineraryVersionRead.model_rebuild()
TripRead.model_rebuild()
PublicTripResponse.model_rebuild()
