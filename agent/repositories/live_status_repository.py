import datetime
from sqlalchemy import update
from sqlalchemy.orm import Session
from database.models import ATMLiveStatus

class LiveStatusRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_atm_id(self, atm_id: int) -> ATMLiveStatus:
        """Retrieves the current live operational status snapshot record for an ATM."""
        return self.session.query(ATMLiveStatus).filter(ATMLiveStatus.ATMId == atm_id).first()

    def save(self, status: ATMLiveStatus) -> None:
        """Saves/Updates the current live operational snapshot."""
        self.session.add(status)
        self.session.flush()

    def update_live_status(self, status: ATMLiveStatus, original_version: bytes) -> bool:
        """
        Updates the ATMLiveStatus row if the current database RowVersion matches 
        original_version, implementing optimistic concurrency.
        Returns True if updated, False otherwise (concurrency conflict).
        """
        if original_version is None:
            self.save(status)
            return True

        stmt = update(ATMLiveStatus).where(
            ATMLiveStatus.ATMId == status.ATMId,
            ATMLiveStatus.RowVersion == original_version
        ).values(
            IsOnline=status.IsOnline,
            CurrentStatus=status.CurrentStatus,
            SSTStatus=status.SSTStatus,
            SupervisorMode=status.SupervisorMode,
            LastHeartbeat=status.LastHeartbeat,
            LastAgentHeartbeat=status.LastAgentHeartbeat,
            LastEventType=status.LastEventType,
            LastEventTime=status.LastEventTime,
            LastTransactionTime=status.LastTransactionTime,
            LastTransactionAmount=status.LastTransactionAmount,
            CardReaderStatus=status.CardReaderStatus,
            RejectBinStatus=status.RejectBinStatus,
            CashAvailable=status.CashAvailable,
            TotalRemainingNotes=status.TotalRemainingNotes,
            CashRemainingAmount=status.CashRemainingAmount,
            Cassette1Status=status.Cassette1Status,
            Cassette1RemainingNotes=status.Cassette1RemainingNotes,
            Cassette2Status=status.Cassette2Status,
            Cassette2RemainingNotes=status.Cassette2RemainingNotes,
            Cassette3Status=status.Cassette3Status,
            Cassette3RemainingNotes=status.Cassette3RemainingNotes,
            Cassette4Status=status.Cassette4Status,
            Cassette4RemainingNotes=status.Cassette4RemainingNotes,
            LastErrorMessage=status.LastErrorMessage,
            UpdatedOn=datetime.datetime.now()
        )
        result = self.session.execute(stmt)
        self.session.flush()
        return result.rowcount > 0
