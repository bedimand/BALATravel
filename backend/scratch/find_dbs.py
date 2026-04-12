import os
import sqlite3

def find_dbs():
    for root, dirs, files in os.walk('.'):
        for file in files:
            if file.endswith('.db'):
                full_path = os.path.join(root, file)
                print(f"--- DB Found: {full_path} ---")
                try:
                    conn = sqlite3.connect(full_path)
                    cursor = conn.cursor()
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                    tables = [row[0] for row in cursor.fetchall()]
                    print(f"Tables: {tables}")
                    if 'places' in tables:
                        cursor.execute("PRAGMA table_info(places)")
                        cols = [row[1] for row in cursor.fetchall()]
                        print(f"Columns in 'places': {cols}")
                    conn.close()
                except Exception as e:
                    print(f"Error reading {full_path}: {e}")

if __name__ == "__main__":
    find_dbs()
