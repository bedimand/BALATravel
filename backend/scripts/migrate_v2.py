"""Safe SQLite migration — adds new columns if they don't exist."""
import sqlite3
import pathlib

DB = pathlib.Path(__file__).parent.parent / "balatravel.db"

NEW_COLUMNS = {
    "trips": [
        ("accommodation_name", "TEXT"),
        ("accommodation_address", "TEXT"),
        ("accommodation_lat", "REAL"),
        ("accommodation_lng", "REAL"),
        ("age_range", "TEXT"),
        ("traveler_sex", "TEXT"),
        ("travel_pace", "TEXT"),
        ("dietary_restrictions", "TEXT DEFAULT '[]'"),
        ("mobility_notes", "TEXT"),
        ("languages", "TEXT DEFAULT '[]'"),
    ],
    "places": [
        ("photos_json", "TEXT DEFAULT '[]'"),
        ("price_level", "INTEGER"),
        ("user_ratings_total", "INTEGER"),
        ("website", "TEXT"),
        ("phone", "TEXT"),
        ("address_full", "TEXT"),
        ("google_place_id", "TEXT"),
        ("editorial_note", "TEXT"),
        ("neighborhood", "TEXT"),
        ("interest_tags", "TEXT DEFAULT '[]'"),
    ],
}

conn = sqlite3.connect(DB)
cur = conn.cursor()
for table, columns in NEW_COLUMNS.items():
    existing = {row[1] for row in cur.execute(f"PRAGMA table_info({table})")}
    for col, col_type in columns:
        if col not in existing:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
            print(f"  + {table}.{col}")
conn.commit()
conn.close()
print("Migration complete.")
