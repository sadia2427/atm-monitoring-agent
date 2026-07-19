from typing import Optional
from sqlalchemy.orm import Session
from database.models import CassetteBalanceHistory

class CassetteRepository:
    def __init__(self, session: Session):
        self.session = session

    def insert_history(self, history: CassetteBalanceHistory) -> None:
        """Appends a new cassette balance/counts snapshot event to history."""
        self.session.add(history)
        self.session.flush()

    def duplicate_snapshot_check(self, atm_id: int, sequence_number: Optional[int], cassette_no: int) -> bool:
        """Checks if a cassette snapshot already exists for the given sequence number and cassette position."""
        if sequence_number is None:
            return False
        return self.session.query(CassetteBalanceHistory).filter(
            CassetteBalanceHistory.ATMId == atm_id,
            CassetteBalanceHistory.EventSequenceNumber == sequence_number,
            CassetteBalanceHistory.CassetteNo == cassette_no
        ).first() is not None
