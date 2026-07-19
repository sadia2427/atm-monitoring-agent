from sqlalchemy.orm import Session
from database.models import AgentHealthLog

class HealthRepository:
    def __init__(self, session: Session):
        self.session = session

    def insert_log(self, log: AgentHealthLog) -> None:
        """Appends a new agent lifecycle, heartbeat, or error log record to history."""
        self.session.add(log)
        self.session.flush()
