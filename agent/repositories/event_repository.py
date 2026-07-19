from sqlalchemy.orm import Session
from database.models import ATMEvent

class EventRepository:
    def __init__(self, session: Session):
        self.session = session

    def insert_event(self, event: ATMEvent) -> None:
        """Inserts an ATMEvent record into the events history table."""
        self.session.add(event)
        self.session.flush()

    def get_event_by_sequence(self, atm_id: int, sequence_number: int) -> ATMEvent:
        """Retrieves a stored ATMEvent using its unique sequence number to prevent duplicates."""
        return self.session.query(ATMEvent).filter(
            ATMEvent.ATMId == atm_id,
            ATMEvent.EventSequenceNumber == sequence_number
        ).first()

    def duplicate_check(self, atm_id: int, sequence_number: int) -> bool:
        """Returns True if the event sequence number already exists for the ATM."""
        if sequence_number is None:
            return False
        return self.session.query(ATMEvent).filter(
            ATMEvent.ATMId == atm_id,
            ATMEvent.EventSequenceNumber == sequence_number
        ).first() is not None
