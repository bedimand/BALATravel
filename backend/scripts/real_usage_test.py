"""End-to-end REAL usage test — no mocks.

Exercises the platform exactly like a user would, but against the REAL agent
(Claude Sonnet 4.5 via the configured OpenAI-compatible endpoint) and the REAL
providers (SerpAPI flights/hotels, OpenTripMap places, OpenWeather, Google Routes).

It:
  1. Creates a trip with realistic inputs (profile, dates, budget, interests).
  2. Runs the autonomous agent to build the initial itinerary (synchronous call).
  3. Sends a chat message to request a change, then approves it.
  4. Prints the final day-by-day itinerary for human inspection.

Run:  .venv/Scripts/python.exe scripts/real_usage_test.py
Requires a populated .env (OPENAI_API_KEY, SERPAPI_API_KEY, OPENTRIPMAP_API_KEY, ...).

This is a manual/diagnostic script, NOT part of the pytest suite (the suite mocks
the LLM and providers, which would defeat the purpose).
"""
from __future__ import annotations

import os
import sys
from datetime import date, time, timedelta
from pathlib import Path

# Windows console defaults to cp1252; force UTF-8 so emojis/arrows don't crash.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# Use a throwaway DB so we never touch real data.
_DB = Path(__file__).resolve().parent / "_real_usage_test.db"
if _DB.exists():
    _DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{_DB.as_posix()}"

# Ensure the backend package is importable when run from repo root or backend/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import Base, engine, SessionLocal  # noqa: E402
from app.api.deps import ensure_local_user  # noqa: E402
from app.models.entities import Trip  # noqa: E402
from app.services.workflow import WorkflowService  # noqa: E402
from app.services.agent_tools import get_active_itinerary  # noqa: E402


def _hr(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def _print_itinerary(trip: Trip) -> None:
    active = get_active_itinerary(trip)
    if not active:
        print("  (sem itinerário ativo)")
        return
    print(f"  Versão {active.version} | resumo: {active.assistant_summary}")
    if active.warnings:
        print(f"  ⚠ warnings: {active.warnings}")
    from collections import defaultdict
    by_day: dict = defaultdict(list)
    for item in active.items:
        by_day[item.date].append(item)
    for day in sorted(by_day):
        print(f"\n  📅 {day.isoformat()}")
        for it in sorted(by_day[day], key=lambda x: x.start_time):
            t = f"{it.start_time.strftime('%H:%M')}-{it.end_time.strftime('%H:%M')}"
            travel = f"  (🚗 {it.travel_time_min}min)" if it.travel_time_min else ""
            print(f"    {t}  [{it.item_type}] {it.title}{travel}")


def main() -> int:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    user = ensure_local_user(db)
    svc = WorkflowService(user)

    start = date.today() + timedelta(days=30)
    end = start + timedelta(days=2)  # 3-day trip

    _hr("1. CRIANDO VIAGEM (inputs reais)")
    trip = Trip(
        user_id=user.id,
        destination="Lisboa",
        currency="EUR",
        locale="pt-BR",
        start_date=start,
        end_date=end,
        budget=1500,
        style="Equilibrado",
        interests=["Gastronomia", "Historia", "Arte e Museus"],
        age_range="26-35",
        traveler_sex="Masculino",
        travel_pace="Equilibrado",
        dietary_restrictions=["Vegetariano"],
        languages=["pt", "en"],
        has_car=False,
        daily_start_time=time(9, 0),
        daily_end_time=time(22, 0),
    )
    db.add(trip)
    db.commit()
    db.refresh(trip)
    svc.initialize_trip(db, trip.id)
    print(f"  Trip #{trip.id}: {trip.destination} | {start} → {end} | €{trip.budget}")
    print(f"  Perfil: {trip.age_range}, {trip.traveler_sex}, ritmo={trip.travel_pace}")
    print(f"  Dieta: {trip.dietary_restrictions} | idiomas: {trip.languages} | carro: {trip.has_car}")
    print(f"  Interesses: {trip.interests}")

    _hr("2. RODANDO O AGENTE REAL (busca + monta roteiro)")
    print("  ... isso chama o LLM e os providers de verdade, pode levar minutos ...")
    result = svc.start(db, trip.id, run_type="setup")
    print(f"  Stage final: {result.workflow.current_stage} / {result.workflow.stage_status}")
    trip = svc._load_trip(db, trip.id)
    _print_itinerary(trip)

    _hr("3. ALTERAÇÃO VIA CHAT (pedido em linguagem natural)")
    msg = "O segundo dia está muito puxado. Pode deixar a tarde mais leve e incluir um café tranquilo?"
    print(f"  Usuário: \"{msg}\"")
    svc.message(db, trip.id, msg)
    trip = svc._load_trip(db, trip.id)
    pending = [d for d in trip.decision_requests if d.status == "pending"]
    if pending:
        d = pending[-1]
        print(f"  → Agente propôs: [{d.kind}] {d.title} — {d.summary}")
        try:
            svc.decide(db, trip.id, d.id, "approve")
            print("  → Usuário aprovou e a mudança foi aplicada.")
        except Exception as exc:
            db.rollback()
            print(f"  → ⚠ FALHA ao aplicar a proposta aprovada: {type(exc).__name__}: {exc}")
    else:
        print("  → Nenhuma proposta gerada (o agente não encontrou mudança a propor).")

    _hr("4. ROTEIRO FINAL")
    trip = svc._load_trip(db, trip.id)
    _print_itinerary(trip)

    db.close()
    print("\n(Concluído. DB temporário:", _DB, ")")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
