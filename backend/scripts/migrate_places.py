import sqlite3
import os

DB_PATH = "balatravel.db"

def migrate():
    if not os.path.exists(DB_PATH):
        print(f"Error: {DB_PATH} not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check current columns
    cursor.execute("PRAGMA table_info(places)")
    existing_cols = [row[1] for row in cursor.fetchall()]
    
    new_cols = [
        ("photos_json", "JSON"),
        ("price_level", "INTEGER"),
        ("user_ratings_total", "INTEGER"),
        ("website", "TEXT"),
        ("phone", "VARCHAR(40)"),
        ("address_full", "TEXT"),
        ("google_place_id", "VARCHAR(200)"),
        ("editorial_note", "TEXT"),
        ("neighborhood", "VARCHAR(80)"),
        ("interest_tags", "JSON")
    ]
    
    added_count = 0
    for col_name, col_type in new_cols:
        if col_name not in existing_cols:
            print(f"Adding column {col_name} to places...")
            try:
                cursor.execute(f"ALTER TABLE places ADD COLUMN {col_name} {col_type}")
                added_count += 1
            except Exception as e:
                print(f"Failed to add {col_name}: {e}")
                
    conn.commit()
    conn.close()
    print(f"Migration complete. Added {added_count} columns.")

if __name__ == "__main__":
    migrate()
