import sqlite3

def check_db():
    try:
        conn = sqlite3.connect('balatravel.db')
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(places)")
        columns = [row[1] for row in cursor.fetchall()]
        print("Columns in 'places':", columns)
        
        target_columns = [
            'price_level', 'user_ratings_total', 'website', 
            'address_full', 'editorial_note', 'neighborhood'
        ]
        
        missing = [c for c in target_columns if c not in columns]
        if missing:
            print("MISSING COLUMNS:", missing)
        else:
            print("All columns present!")
            
        conn.close()
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    check_db()
