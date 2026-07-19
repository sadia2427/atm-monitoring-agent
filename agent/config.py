import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
from utils.paths import get_env_file_path

# Resolve .env file using centralized path resolution (supports frozen executables)
env_path = get_env_file_path()

class AgentConfig(BaseSettings):
    atm_terminal_id: str
    agent_name: Optional[str] = "DefaultAgent"
    
    # DB configuration parameters
    db_server: str = "localhost\\SQLEXPRESS"
    db_database: str = "ATMMonitoring"
    db_username: Optional[str] = None
    db_password: Optional[str] = None
    db_driver: str = "ODBC Driver 17 for SQL Server"
    db_trusted_connection: str = "yes"
    db_trust_server_certificate: str = "yes"
    
    # Direct database connection URL override
    database_url: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=env_path,
        env_file_encoding="utf-8",
        extra="ignore"
    )

# Instantiate config
config = AgentConfig()
