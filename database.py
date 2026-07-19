import os
import urllib.parse
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.ext.declarative import declarative_base

# Helper to load .env manually to ensure compatibility without external library dependencies
def load_env():
    if os.path.exists(".env"):
        with open(".env", "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

# Helper to check and create database if not exists on SQL Server
def create_database_if_not_exists():
    db_url = os.getenv("DATABASE_URL")
    if db_url and "sqlite" in db_url:
        return
        
    db_server = os.getenv("DB_SERVER", "127.0.0.1")
    db_database = os.getenv("DB_DATABASE", "monitor_db")
    db_username = os.getenv("DB_USERNAME", "")
    db_password = os.getenv("DB_PASSWORD", "")
    db_driver = os.getenv("DB_DRIVER", "SQL Server")
    db_trusted = os.getenv("DB_TRUSTED_CONNECTION", "no")

    if not (db_driver.startswith("{") and db_driver.endswith("}")):
        db_driver = f"{{{db_driver}}}"

    conn_str = f"DRIVER={db_driver};SERVER={db_server};DATABASE=master;"
    if db_trusted.lower() == "yes":
        conn_str += "Trusted_Connection=yes;"
    if db_username and db_password:
        conn_str += f"UID={db_username};PWD={db_password};"

    try:
        import pyodbc
        conn = pyodbc.connect(conn_str, autocommit=True)
        cursor = conn.cursor()
        cursor.execute(f"IF NOT EXISTS (SELECT * FROM sys.databases WHERE name = '{db_database}') CREATE DATABASE [{db_database}]")
        cursor.close()
        conn.close()
        print(f"[DB Startup] Database '{db_database}' checked/created successfully.")
    except Exception as e:
        print(f"[DB Startup] Warning: Could not verify/create database '{db_database}' on master: {e}")

load_env()
create_database_if_not_exists()

# Read configurations
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    db_server = os.getenv("DB_SERVER", "127.0.0.1")
    db_database = os.getenv("DB_DATABASE", "monitor_db")
    db_username = os.getenv("DB_USERNAME", "")
    db_password = os.getenv("DB_PASSWORD", "")
    db_driver = os.getenv("DB_DRIVER", "SQL Server")
    db_trusted = os.getenv("DB_TRUSTED_CONNECTION", "no")
    db_trust_cert = os.getenv("DB_TRUST_SERVER_CERTIFICATE", "yes")

    # Safe url-encode the driver name to handle spaces
    safe_driver = urllib.parse.quote_plus(db_driver)

    # Build query parameters
    query_params = f"driver={safe_driver}"
    if db_trusted.lower() == "yes":
        query_params += "&trusted_connection=yes"
    # Legacy 'SQL Server' driver does not support TrustServerCertificate
    if db_trust_cert.lower() == "yes" and db_driver.strip("{}") != "SQL Server":
        query_params += "&TrustServerCertificate=yes"

    if db_username and db_password:
        safe_user = urllib.parse.quote_plus(db_username)
        safe_pass = urllib.parse.quote_plus(db_password)
        DATABASE_URL = f"mssql+aioodbc://{safe_user}:{safe_pass}@{db_server}/{db_database}?{query_params}"
    else:
        DATABASE_URL = f"mssql+aioodbc://@{db_server}/{db_database}?{query_params}"

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
