from sqlalchemy.orm import Session
from database.models import AgentFileState

class AgentRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_file_state(self, atm_id: int, file_path: str) -> AgentFileState:
        """Retrieves parsing offsets and properties for a given file on an ATM."""
        return self.session.query(AgentFileState).filter(
            AgentFileState.ATMId == atm_id,
            AgentFileState.FilePath == file_path
        ).first()

    def create_file_state(self, file_state: AgentFileState) -> None:
        """Saves a new file parsing progress state record."""
        self.session.add(file_state)
        self.session.flush()

    def update_file_state(self, file_state: AgentFileState) -> None:
        """Updates an existing parsing offset record."""
        self.session.add(file_state)
        self.session.flush()
