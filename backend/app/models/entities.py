from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, Time, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    locale: Mapped[str] = mapped_column(String(10), default="pt-BR")
    currency: Mapped[str] = mapped_column(String(3), default="BRL")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    preference: Mapped["TravelPreference | None"] = relationship(back_populates="user", cascade="all, delete-orphan", uselist=False)
    trips: Mapped[list["Trip"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class TravelPreference(Base):
    __tablename__ = "travel_preferences"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    budget_range: Mapped[str | None] = mapped_column(String(50), nullable=True)
    styles: Mapped[list[str]] = mapped_column(JSON, default=list)
    interests: Mapped[list[str]] = mapped_column(JSON, default=list)
    notification_settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    user: Mapped["User"] = relationship(back_populates="preference")


class Trip(Base):
    __tablename__ = "trips"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    destination: Mapped[str] = mapped_column(String(120))
    currency: Mapped[str] = mapped_column(String(3), default="BRL")
    locale: Mapped[str] = mapped_column(String(10), default="pt-BR")
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    budget: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    style: Mapped[str] = mapped_column(String(50))
    interests: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(30), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Accommodation fields (where the traveler is staying)
    accommodation_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    accommodation_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    accommodation_lat: Mapped[float | None] = mapped_column(nullable=True)
    accommodation_lng: Mapped[float | None] = mapped_column(nullable=True)
    # Preferences and Logisitics
    has_car: Mapped[bool] = mapped_column(Boolean, default=False)
    daily_start_time: Mapped[time] = mapped_column(Time, default=time(9, 0))
    daily_end_time: Mapped[time] = mapped_column(Time, default=time(22, 0))
    # Personal traveler profile
    age_range: Mapped[str | None] = mapped_column(String(20), nullable=True)
    traveler_sex: Mapped[str | None] = mapped_column(String(30), nullable=True)
    travel_pace: Mapped[str | None] = mapped_column(String(30), nullable=True)
    dietary_restrictions: Mapped[list[str]] = mapped_column(JSON, default=list)
    mobility_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    languages: Mapped[list[str]] = mapped_column(JSON, default=list)

    user: Mapped["User"] = relationship(back_populates="trips")
    places: Mapped[list["Place"]] = relationship(back_populates="trip", cascade="all, delete-orphan")
    itinerary_versions: Mapped[list["ItineraryVersion"]] = relationship(back_populates="trip", cascade="all, delete-orphan")
    notifications: Mapped[list["Notification"]] = relationship(back_populates="trip", cascade="all, delete-orphan")
    exports: Mapped[list["Export"]] = relationship(back_populates="trip", cascade="all, delete-orphan")
    share_links: Mapped[list["ShareLink"]] = relationship(back_populates="trip", cascade="all, delete-orphan")
    agent_runs: Mapped[list["AgentRun"]] = relationship(back_populates="trip", cascade="all, delete-orphan")
    plan_mutations: Mapped[list["PlanMutation"]] = relationship(back_populates="trip", cascade="all, delete-orphan")
    workflow_state: Mapped["TripWorkflowState | None"] = relationship(
        back_populates="trip",
        cascade="all, delete-orphan",
        uselist=False,
    )
    workflow_runs: Mapped[list["WorkflowRun"]] = relationship(back_populates="trip", cascade="all, delete-orphan")
    decision_requests: Mapped[list["DecisionRequest"]] = relationship(back_populates="trip", cascade="all, delete-orphan")
    artifacts: Mapped[list["AgentArtifact"]] = relationship(back_populates="trip", cascade="all, delete-orphan")
    weather_snapshots: Mapped[list["TripWeatherSnapshot"]] = relationship(back_populates="trip", cascade="all, delete-orphan")
    route_estimates: Mapped[list["RouteEstimateCache"]] = relationship(back_populates="trip", cascade="all, delete-orphan")


class Place(Base):
    __tablename__ = "places"
    __table_args__ = (UniqueConstraint("trip_id", "external_id", name="uq_trip_place"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(50))
    lat: Mapped[float] = mapped_column()
    lng: Mapped[float] = mapped_column()
    opening_hours_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    rating: Mapped[float] = mapped_column(default=4.0)
    estimated_duration: Mapped[int] = mapped_column(Integer, default=120)
    is_selected: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(50))
    confidence: Mapped[float] = mapped_column(default=0.88)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    deeplink: Mapped[str] = mapped_column(Text)
    photos_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    price_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user_ratings_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    address_full: Mapped[str | None] = mapped_column(Text, nullable=True)
    google_place_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    editorial_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    neighborhood: Mapped[str | None] = mapped_column(String(80), nullable=True)
    interest_tags: Mapped[list[str]] = mapped_column(JSON, default=list)

    trip: Mapped["Trip"] = relationship(back_populates="places")

    @property
    def hours_confidence(self) -> float:
        if self.opening_hours_json:
            return 0.85
        return 0.35


class ItineraryVersion(Base):
    __tablename__ = "itinerary_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(30), default="draft")
    total_estimated_cost: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    assistant_summary: Mapped[str] = mapped_column(Text, default="")
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    trip: Mapped["Trip"] = relationship(back_populates="itinerary_versions")
    items: Mapped[list["ItineraryItem"]] = relationship(back_populates="itinerary_version", cascade="all, delete-orphan")
    source_mutations: Mapped[list["PlanMutation"]] = relationship(
        back_populates="from_itinerary_version",
        cascade="all, delete-orphan",
        foreign_keys="PlanMutation.from_itinerary_version_id",
    )
    target_mutations: Mapped[list["PlanMutation"]] = relationship(
        back_populates="to_itinerary_version",
        cascade="all, delete-orphan",
        foreign_keys="PlanMutation.to_itinerary_version_id",
    )


class ItineraryItem(Base):
    __tablename__ = "itinerary_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    itinerary_version_id: Mapped[int] = mapped_column(ForeignKey("itinerary_versions.id"), index=True)
    date: Mapped[date] = mapped_column(Date)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    item_type: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(120))
    place_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lat: Mapped[float | None] = mapped_column(nullable=True)
    lng: Mapped[float | None] = mapped_column(nullable=True)
    travel_time_min: Mapped[int] = mapped_column(Integer, default=0)
    travel_distance_km: Mapped[float] = mapped_column(default=0.0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    curator_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)

    itinerary_version: Mapped["ItineraryVersion"] = relationship(back_populates="items")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id"), index=True)
    notification_type: Mapped[str] = mapped_column(String(40))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    channel: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="pending")

    trip: Mapped["Trip"] = relationship(back_populates="notifications")


class Export(Base):
    __tablename__ = "exports"

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id"), index=True)
    format: Mapped[str] = mapped_column(String(10), default="pdf")
    file_url: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    trip: Mapped["Trip"] = relationship(back_populates="exports")


class ShareLink(Base):
    __tablename__ = "share_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id"), index=True)
    token: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    trip: Mapped["Trip"] = relationship(back_populates="share_links")


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id"), index=True)
    intent: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="running")
    user_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    assistant_message: Mapped[str] = mapped_column(Text, default="")
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    applied_changes: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    model: Mapped[str] = mapped_column(String(120), default="openrouter/auto")
    prompt_version: Mapped[str] = mapped_column(String(20), default="v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    trip: Mapped["Trip"] = relationship(back_populates="agent_runs")
    tool_calls: Mapped[list["AgentToolCall"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    mutations: Mapped[list["PlanMutation"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class AgentToolCall(Base):
    __tablename__ = "agent_tool_calls"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    tool_name: Mapped[str] = mapped_column(String(80))
    arguments_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    run: Mapped["AgentRun"] = relationship(back_populates="tool_calls")


class PlanMutation(Base):
    __tablename__ = "plan_mutations"

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id"), index=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True, index=True)
    from_itinerary_version_id: Mapped[int | None] = mapped_column(ForeignKey("itinerary_versions.id"), nullable=True)
    to_itinerary_version_id: Mapped[int | None] = mapped_column(ForeignKey("itinerary_versions.id"), nullable=True)
    mutation_type: Mapped[str] = mapped_column(String(40))
    rationale: Mapped[str] = mapped_column(Text, default="")
    changed_item_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    trip: Mapped["Trip"] = relationship(back_populates="plan_mutations")
    run: Mapped["AgentRun | None"] = relationship(back_populates="mutations")
    from_itinerary_version: Mapped["ItineraryVersion | None"] = relationship(
        back_populates="source_mutations",
        foreign_keys=[from_itinerary_version_id],
    )
    to_itinerary_version: Mapped["ItineraryVersion | None"] = relationship(
        back_populates="target_mutations",
        foreign_keys=[to_itinerary_version_id],
    )


class TripWorkflowState(Base):
    __tablename__ = "trip_workflow_states"

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id"), unique=True, index=True)
    current_stage: Mapped[str] = mapped_column(String(60), default="planning")
    stage_status: Mapped[str] = mapped_column(String(20), default="idle")
    active_workflow_run_id: Mapped[int | None] = mapped_column(ForeignKey("workflow_runs.id"), nullable=True)
    last_user_goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    trip: Mapped["Trip"] = relationship(back_populates="workflow_state")


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id"), index=True)
    run_type: Mapped[str] = mapped_column(String(40), default="setup")
    status: Mapped[str] = mapped_column(String(20), default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    trip: Mapped["Trip"] = relationship(back_populates="workflow_runs")
    steps: Mapped[list["WorkflowStep"]] = relationship(back_populates="workflow_run", cascade="all, delete-orphan")
    decisions: Mapped[list["DecisionRequest"]] = relationship(back_populates="workflow_run", cascade="all, delete-orphan")
    artifacts: Mapped[list["AgentArtifact"]] = relationship(back_populates="workflow_run", cascade="all, delete-orphan")


class WorkflowStep(Base):
    __tablename__ = "workflow_steps"

    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_run_id: Mapped[int] = mapped_column(ForeignKey("workflow_runs.id"), index=True)
    step_key: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(20), default="running")
    summary: Mapped[str] = mapped_column(Text, default="")
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    output_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    workflow_run: Mapped["WorkflowRun"] = relationship(back_populates="steps")


class DecisionRequest(Base):
    __tablename__ = "decision_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id"), index=True)
    workflow_run_id: Mapped[int | None] = mapped_column(ForeignKey("workflow_runs.id"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    title: Mapped[str] = mapped_column(String(120), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    options_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    recommended_option_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    selected_option_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    trip: Mapped["Trip"] = relationship(back_populates="decision_requests")
    workflow_run: Mapped["WorkflowRun | None"] = relationship(back_populates="decisions")


class AgentArtifact(Base):
    __tablename__ = "agent_artifacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id"), index=True)
    workflow_run_id: Mapped[int | None] = mapped_column(ForeignKey("workflow_runs.id"), nullable=True, index=True)
    artifact_type: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(120), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    trip: Mapped["Trip"] = relationship(back_populates="artifacts")
    workflow_run: Mapped["WorkflowRun | None"] = relationship(back_populates="artifacts")


class TripWeatherSnapshot(Base):
    __tablename__ = "trip_weather_snapshots"
    __table_args__ = (UniqueConstraint("trip_id", "forecast_date", name="uq_trip_weather_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id"), index=True)
    forecast_date: Mapped[date] = mapped_column(Date)
    condition_label: Mapped[str] = mapped_column(String(80), default="")
    temp_min_c: Mapped[float | None] = mapped_column(nullable=True)
    temp_max_c: Mapped[float | None] = mapped_column(nullable=True)
    rain_probability: Mapped[float] = mapped_column(default=0.0)
    is_outdoor_risky: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(40), default="fallback")
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    trip: Mapped["Trip"] = relationship(back_populates="weather_snapshots")


class RouteEstimateCache(Base):
    __tablename__ = "route_estimate_cache"
    __table_args__ = (
        UniqueConstraint("trip_id", "origin_key", "destination_key", "travel_mode", name="uq_trip_route_pair"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id"), index=True)
    origin_key: Mapped[str] = mapped_column(String(160))
    destination_key: Mapped[str] = mapped_column(String(160))
    travel_mode: Mapped[str] = mapped_column(String(20), default="drive")
    duration_min: Mapped[int] = mapped_column(Integer, default=0)
    distance_km: Mapped[float] = mapped_column(default=0.0)
    source: Mapped[str] = mapped_column(String(40), default="fallback")
    encoded_polyline: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    trip: Mapped["Trip"] = relationship(back_populates="route_estimates")
