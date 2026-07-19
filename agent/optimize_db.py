import pyodbc
import os

# Load database settings from .env
if os.path.exists(".env"):
    with open(".env", "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

db_server = os.getenv("DB_SERVER", "localhost\\SQLEXPRESS")
db_driver = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")

conn_str = f"DRIVER={{{db_driver}}};SERVER={db_server};DATABASE=master;Trusted_Connection=yes;"

try:
    conn = pyodbc.connect(conn_str, autocommit=True)
    cursor = conn.cursor()
    print("Setting database DELAYED_DURABILITY = FORCED...")
    cursor.execute("ALTER DATABASE ATMMonitoring SET DELAYED_DURABILITY = FORCED;")
    print("Database optimization applied successfully!")
    cursor.close()
    conn.close()
except Exception as e:
    print(f"Error applying SQL Server database optimization: {e}")
