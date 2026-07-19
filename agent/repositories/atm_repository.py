from sqlalchemy.orm import Session
from database.models import ATM

class ATMRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, id: int) -> ATM:
        """Retrieves an ATM record by its internal integer ID."""
        return self.session.query(ATM).filter(ATM.Id == id).first()

    def get_by_terminal_id(self, terminal_id: str) -> ATM:
        """Retrieves an ATM record by its unique hardware TerminalId."""
        return self.session.query(ATM).filter(ATM.TerminalId == terminal_id).first()

    def update(self, atm: ATM) -> None:
        """Saves/Updates ATM details."""
        self.session.add(atm)
        self.session.flush()
