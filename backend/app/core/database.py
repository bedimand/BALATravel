from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


settings = get_settings()
connect_args = {"check_same_thread": False, "timeout": 15.0} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    future=True,
    # Background workflow/agent threads each hold a session while doing slow LLM
    # work, and the trip page polls frequently; the default pool (5 + 10) drains
    # and times out. Give it real headroom, drop dead connections (Render closes
    # idle TCP), and recycle long-lived ones.
    pool_size=20,
    max_overflow=40,
    pool_timeout=30,
    pool_recycle=1800,
    pool_pre_ping=True,
)

if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=15000")
        cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

class Base(DeclarativeBase):
    pass


def ensure_sqlite_schema() -> None:
    if not settings.database_url.startswith("sqlite"):
        return

    with engine.begin() as connection:
        table_names = {
            row[0]
            for row in connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "trips" not in table_names:
            return

        trip_columns = {
            row[1]
            for row in connection.exec_driver_sql("PRAGMA table_info(trips)")
        }
        if "currency" not in trip_columns:
            connection.exec_driver_sql("ALTER TABLE trips ADD COLUMN currency VARCHAR(3) NOT NULL DEFAULT 'BRL'")
        if "locale" not in trip_columns:
            connection.exec_driver_sql("ALTER TABLE trips ADD COLUMN locale VARCHAR(10) NOT NULL DEFAULT 'pt-BR'")

        if "places" in table_names:
            place_columns = {
                row[1]
                for row in connection.exec_driver_sql("PRAGMA table_info(places)")
            }
            if "is_selected" not in place_columns:
                connection.exec_driver_sql("ALTER TABLE places ADD COLUMN is_selected BOOLEAN NOT NULL DEFAULT 0")
            if "image_url" not in place_columns:
                connection.exec_driver_sql("ALTER TABLE places ADD COLUMN image_url TEXT")
            if "photos_json" not in place_columns:
                connection.exec_driver_sql("ALTER TABLE places ADD COLUMN photos_json JSON DEFAULT '[]'")
            if "price_level" not in place_columns:
                connection.exec_driver_sql("ALTER TABLE places ADD COLUMN price_level INTEGER")
            if "user_ratings_total" not in place_columns:
                connection.exec_driver_sql("ALTER TABLE places ADD COLUMN user_ratings_total INTEGER")
            if "website" not in place_columns:
                connection.exec_driver_sql("ALTER TABLE places ADD COLUMN website TEXT")
            if "phone" not in place_columns:
                connection.exec_driver_sql("ALTER TABLE places ADD COLUMN phone VARCHAR(40)")
            if "address_full" not in place_columns:
                connection.exec_driver_sql("ALTER TABLE places ADD COLUMN address_full TEXT")
            if "google_place_id" not in place_columns:
                connection.exec_driver_sql("ALTER TABLE places ADD COLUMN google_place_id VARCHAR(200)")
            if "editorial_note" not in place_columns:
                connection.exec_driver_sql("ALTER TABLE places ADD COLUMN editorial_note TEXT")
            if "neighborhood" not in place_columns:
                connection.exec_driver_sql("ALTER TABLE places ADD COLUMN neighborhood VARCHAR(80)")
            if "interest_tags" not in place_columns:
                connection.exec_driver_sql("ALTER TABLE places ADD COLUMN interest_tags JSON DEFAULT '[]'")

        if "itinerary_items" in table_names:
            itinerary_item_columns = {
                row[1]
                for row in connection.exec_driver_sql("PRAGMA table_info(itinerary_items)")
            }
            if "travel_distance_km" not in itinerary_item_columns:
                connection.exec_driver_sql("ALTER TABLE itinerary_items ADD COLUMN travel_distance_km FLOAT NOT NULL DEFAULT 0")
            if "curator_reasoning" not in itinerary_item_columns:
                connection.exec_driver_sql("ALTER TABLE itinerary_items ADD COLUMN curator_reasoning TEXT")

        if "route_estimate_cache" in table_names:
            route_columns = {
                row[1]
                for row in connection.exec_driver_sql("PRAGMA table_info(route_estimate_cache)")
            }
            if "encoded_polyline" not in route_columns:
                connection.exec_driver_sql("ALTER TABLE route_estimate_cache ADD COLUMN encoded_polyline TEXT")


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
