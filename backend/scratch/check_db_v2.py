import sqlite3

def list_tables():
    try:
        conn = sqlite3.connect('balatravel.db')
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        print("Tables in 'balatravel.db':", tables)
        
        for table in tables:
            cursor.execute(f"PRAGMA table_info({table})")
            columns = [row[1] for row in cursor.fetchall()]
            print(f"Columns in '{table}':", columns)
            
        conn.close()
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    list_tables()
