"""End-to-end test of step-by-step scheduling via CentralMind autonomous mode."""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, ".")

from datetime import date, time, datetime, UTC
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session as SASession, sessionmaker

from app.core.database import Base
from app.models.entities import Trip, User, WorkflowRun
from app.services.central_mind import CentralMind


engine = create_engine("sqlite:///./test_stepbystep.db", echo=False)
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine)


def log_step(db, run, step_key, status, summary, *args, **kwargs):
    print(f"  [{status}] {step_key}: {summary[:160]}")


def main():
    db: SASession = SessionLocal()

    # Create user
    user = User(name="Test Traveler", email="test@bala.com", password_hash="x")
    db.add(user)
    db.commit()
    db.refresh(user)

    # Create trip - 3 days in Lisbon
    trip = Trip(
        user_id=user.id,
        destination="Lisbon, Portugal",
        origin_city="São Paulo",
        start_date=date(2026, 6, 15),
        end_date=date(2026, 6, 18),
        budget=Decimal("3000"),
        currency="EUR",
        style="cultural",
        interests=["museums", "food", "architecture", "viewpoints"],
        status="planning",
        accommodation_name="Hotel Alfama",
        accommodation_lat=38.7103,
        accommodation_lng=-9.1303,
        has_car=False,
        daily_start_time=time(9, 0),
        daily_end_time=time(22, 0),
        dietary_restrictions=["vegetarian"],
        mobility_notes=None,
        languages=["pt", "en"],
    )
    db.add(trip)
    db.commit()
    db.refresh(trip)

    print(f"Created trip ID={trip.id}: {trip.destination}")
    print(f"  Dates: {trip.start_date} to {trip.end_date} ({(trip.end_date - trip.start_date).days} days)")
    print(f"  Interests: {trip.interests}")
    print(f"  Accommodation: {trip.accommodation_name} ({trip.accommodation_lat}, {trip.accommodation_lng})")
    print()

    # Create workflow run
    run = WorkflowRun(trip_id=trip.id, run_type="autonomous_planning", status="running")
    db.add(run)
    db.commit()
    db.refresh(run)

    # Run autonomous planning
    mind = CentralMind(user)
    print("=" * 60)
    print("STARTING AUTONOMOUS PLANNING (step-by-step scheduling)")
    print("=" * 60)

    try:
        mind.plan_trip(db, trip, run, log_step)
    except Exception as exc:
        print(f"\nERROR: {type(exc).__name__}: {exc}")
        import traceback
        traceback.print_exc()

    # Print history
    print("\n" + "=" * 60)
    print("AGENT HISTORY (all tool calls)")
    print("=" * 60)
    # Get context from mind - we need to capture it
    # For now, just check results

    # Check results
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)

    db.expire_all()
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.entities import ItineraryVersion, ItineraryItem, Place

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
    for p in places[:10]:
        print(f"  - {p.name} ({p.category}) rating={p.rating} selected={p.is_selected}")

    versions = trip.itinerary_versions
    print(f"\nItinerary versions: {len(versions)}")
    for v in versions:
        print(f"  Version {v.version}: status={v.status}, items={len(v.items)}")
        for item in sorted(v.items, key=lambda x: (x.date, x.start_time)):
            print(f"    {item.date} {item.start_time.strftime('%H:%M')}-{item.end_time.strftime('%H:%M')} \"{item.title}\" travel={item.travel_time_min}min/{item.travel_distance_km:.1f}km")

    db.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
