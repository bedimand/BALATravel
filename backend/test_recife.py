"""Test autonomous planning for Recife with the budget/history fixes."""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, ".")

from datetime import date, time
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker, selectinload

from app.core.database import Base
from app.models.entities import ItineraryVersion, Place, Trip, User, WorkflowRun
from app.services.central_mind import CentralMind


engine = create_engine("sqlite:///./test_recife.db", echo=False)
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine)


def log_step(db, run, step_key, status, summary, *args, **kwargs):
    print(f"  [{status}] {step_key}: {summary[:160]}")


def main():
    db = SessionLocal()

    user = User(name="Test Traveler", email="test@bala.com", password_hash="x")
    db.add(user)
    db.commit()
    db.refresh(user)

    trip = Trip(
        user_id=user.id,
        destination="Recife",
        origin_city="Sao Paulo",
        start_date=date(2026, 5, 25),
        end_date=date(2026, 5, 30),
        budget=Decimal("2000"),
        currency="BRL",
        style="Equilibrado",
        interests=["Gastronomia", "Historia", "Praia", "Compras"],
        status="planning",
        accommodation_name="Recife",
        accommodation_lat=-8.0578381,
        accommodation_lng=-34.8828969,
        has_car=False,
        daily_start_time=time(9, 0),
        daily_end_time=time(22, 0),
        dietary_restrictions=[],
        mobility_notes=None,
        languages=["pt"],
    )
    db.add(trip)
    db.commit()
    db.refresh(trip)

    print(f"Created trip ID={trip.id}: {trip.destination}")
    print(f"  Dates: {trip.start_date} to {trip.end_date} ({(trip.end_date - trip.start_date).days} days)")
    print(f"  Interests: {trip.interests}")
    print()

    run = WorkflowRun(trip_id=trip.id, run_type="autonomous_planning", status="running")
    db.add(run)
    db.commit()
    db.refresh(run)

    mind = CentralMind(user)
    print("=" * 60)
    print("STARTING AUTONOMOUS PLANNING")
    print("=" * 60)

    try:
        mind.plan_trip(db, trip, run, log_step)
    except Exception as exc:
        print(f"\nERROR: {type(exc).__name__}: {exc}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)

    db.expire_all()
    trip = db.scalar(
        select(Trip)
        .where(Trip.id == trip.id)
        .options(
            selectinload(Trip.itinerary_versions).selectinload(ItineraryVersion.items),
            selectinload(Trip.places),
        )
    )

    places = list(db.scalars(select(Place).where(Place.trip_id == trip.id)))
    print(f"\nPlaces saved: {len(places)}")
    for p in places[:15]:
        print(f"  - {p.name} ({p.category}) rating={p.rating}")

    versions = trip.itinerary_versions
    print(f"\nItinerary versions: {len(versions)}")
    for v in versions:
        print(f"  Version {v.version}: status={v.status}, items={len(v.items)}")
        days_covered = set()
        for item in sorted(v.items, key=lambda x: (x.date, x.start_time)):
            days_covered.add(item.date)
            print(f"    {item.date} {item.start_time.strftime('%H:%M')}-{item.end_time.strftime('%H:%M')} \"{item.title}\" ({item.item_type})")
        print(f"  Days covered: {len(days_covered)}")

    db.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
