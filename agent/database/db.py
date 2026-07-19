import urllib.parse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from config import config

# 1. Build Connection URL for SQL Server using pyodbc
DATABASE_URL = config.database_url
if not DATABASE_URL:
    db_server = config.db_server
    db_database = config.db_database
    db_driver = config.db_driver
    db_username = config.db_username
    db_password = config.db_password
    db_trusted = config.db_trusted_connection
    db_trust_cert = config.db_trust_server_certificate

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
        DATABASE_URL = f"mssql+pyodbc://{safe_user}:{safe_pass}@{db_server}/{db_database}?{query_params}"
    else:
        # Use Windows Authentication
        DATABASE_URL = f"mssql+pyodbc://@{db_server}/{db_database}?{query_params}"

# 2. Configure engine and session factory
engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

class Base(DeclarativeBase):
    pass

def test_db_connection() -> bool:
    """Verifies that the connection to SQL Server is active."""
    from utils.metrics import metrics_tracker
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        metrics_tracker.record_successful_connection()
        return True
    except Exception as e:
        print(f"Database connection error: {e}")
        metrics_tracker.record_connection_failure()
        return False



