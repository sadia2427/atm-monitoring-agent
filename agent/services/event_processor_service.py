import datetime
import time
from dataclasses import dataclass
from typing import List, Optional
import sqlalchemy.exc
from sqlalchemy.orm import Session
from database.models import ATMEvent, CassetteBalanceHistory, ATMLiveStatus, AgentHealthLog
from repositories.event_repository import EventRepository
from repositories.cassette_repository import CassetteRepository
from repositories.live_status_repository import LiveStatusRepository
from repositories.health_repository import HealthRepository
from models.parser_models import ParserResult, ATMParsedEvent, CassetteSnapshot
from utils.logger import agent_logger

@dataclass
class ProcessingStatistics:
    EventsProcessed: int = 0
    EventsInserted: int = 0
    EventsSkipped: int = 0
    DuplicateEvents: int = 0
    CassetteSnapshotsInserted: int = 0
    LiveStatusUpdates: int = 0
    HealthLogsWritten: int = 0
    DatabaseRetries: int = 0
    ProcessingTimeMs: float = 0.0

class EventProcessorService:
    def __init__(self, session_factory):
        self.session_factory = session_factory
        self._simulate_event_error_seq = None
        self._simulate_concurrency_conflict = False

    def process_result(self, atm_id: int, result: ParserResult) -> ProcessingStatistics:
        """
        Orchestrates database updates for all parsed events in ParserResult.
        Processes each event block in its own independent SQL transaction.
        Returns runtime ProcessingStatistics.
        """
        start_time = time.perf_counter()
        stats = ProcessingStatistics()
        
        agent_logger.info("Processing Started")
        
        # Sort events by ATMId (implied), EventSequenceNumber, and EventTime to guarantee order
        sorted_events = sorted(
            result.events,
            key=lambda x: (x.EventSequenceNumber if x.EventSequenceNumber is not None else 0, x.EventTime)
        )
        
        for ev in sorted_events:
            stats.EventsProcessed += 1
            session = self.session_factory()
            
            try:
                # Start transaction explicitly
                agent_logger.info("Transaction Started")
                session.begin()
                
                event_repo = EventRepository(session)
                cassette_repo = CassetteRepository(session)
                live_status_repo = LiveStatusRepository(session)
                
                # Test hook to fail processing on a specific sequence number
                if self._simulate_event_error_seq == ev.EventSequenceNumber:
                    raise Exception(f"Simulated event processing failure for sequence {ev.EventSequenceNumber}")

                # 1. Idempotency duplicate checks
                is_duplicate = False
                if ev.EventSequenceNumber is not None:
                    is_duplicate = event_repo.duplicate_check(atm_id, ev.EventSequenceNumber)
                    
                if is_duplicate:
                    agent_logger.debug(f"Duplicate Event Skipped: Sequence {ev.EventSequenceNumber}")
                    stats.DuplicateEvents += 1
                    stats.EventsSkipped += 1
                    session.rollback()
                    agent_logger.info("Transaction Rolled Back")
                    continue

                # 2. Insert ATMEvent database row
                db_event = ATMEvent(
                    ATMId=atm_id,
                    EventSequenceNumber=ev.EventSequenceNumber,
                    EventTime=ev.EventTime,
                    EventType=ev.EventType,
                    EventCategory=ev.EventCategory,
                    Severity=ev.Severity,
                    TerminalStatus=ev.TerminalStatus,
                    Message=ev.Message,
                    CardNumberMasked=ev.CardNumberMasked,
                    ResponseCode=ev.ResponseCode,
                    FunctionId=ev.FunctionId,
                    Opcode=ev.Opcode,
                    Amount=ev.Amount,
                    SupervisorMode=ev.SupervisorMode,
                    IsCashAdded=ev.IsCashAdded,
                    IsCashRemoved=ev.IsCashRemoved,
                    IsCassetteInserted=ev.IsCassetteInserted,
                    IsCassetteRemoved=ev.IsCassetteRemoved,
                    IsRejectBinRemoved=ev.IsRejectBinRemoved,
                    IsRejectBinInserted=ev.IsRejectBinInserted,
                    IsCardCaptured=ev.IsCardCaptured,
                    IsTransactionStart=ev.IsTransactionStart,
                    IsTransactionEnd=ev.IsTransactionEnd,
                    RawEvent=ev.RawEvent,
                    SourceFileName=ev.SourceFileName,
                    SourceLineNumber=ev.StartLineNumber,
                    TerminalIdSnapshot=ev.TerminalIdSnapshot
                )
                
                try:
                    event_repo.insert_event(db_event)
                    session.flush()
                    stats.EventsInserted += 1
                except sqlalchemy.exc.IntegrityError:
                    # Gracefully handle unique constraints silently
                    session.rollback()
                    agent_logger.debug(f"Duplicate Event Skipped (IntegrityError): Sequence {ev.EventSequenceNumber}")
                    stats.DuplicateEvents += 1
                    stats.EventsSkipped += 1
                    continue

                # 3. Match and insert CassetteBalanceHistory snapshots
                matching_snaps = [
                    s for s in result.cassette_snapshots
                    if (s.StartLineNumber == ev.StartLineNumber and s.EndLineNumber == ev.EndLineNumber)
                ]

                for snap in matching_snaps:
                    is_dup_snap = cassette_repo.duplicate_snapshot_check(atm_id, ev.EventSequenceNumber, snap.CassetteNo)
                    if is_dup_snap:
                        continue

                    db_snap = CassetteBalanceHistory(
                        ATMId=atm_id,
                        EventId=db_event.Id,
                        EventSequenceNumber=ev.EventSequenceNumber,
                        EventTime=ev.EventTime,
                        CassetteNo=snap.CassetteNo,
                        CassetteStatus=snap.CassetteStatus,
                        Denomination=snap.Denomination,
                        CurrencyCode=snap.CurrencyCode,
                        LoadedNotes=snap.LoadedNotes,
                        RemainingNotes=snap.RemainingNotes,
                        RejectedNotes=snap.RejectedNotes,
                        DispensedNotes=snap.DispensedNotes,
                        CashAmount=snap.CashAmount,
                        OperationType=snap.OperationType,
                        SourceFileName=snap.SourceFileName,
                        SourceLineNumber=snap.StartLineNumber
                    )
                    
                    try:
                        cassette_repo.insert_history(db_snap)
                        stats.CassetteSnapshotsInserted += 1
                    except sqlalchemy.exc.IntegrityError:
                        pass # Ignore duplicate snapshot constraints

                # 4. Update AtmLiveStatus incorporating concurrency retry and timestamp protection
                concurrency_attempts = 2
                concurrency_success = False
                
                for attempt_idx in range(concurrency_attempts):
                    status = live_status_repo.get_by_atm_id(atm_id)
                    original_version = None
                    
                    if not status:
                        agent_logger.info(f"Initializing new AtmLiveStatus record for ATM ID {atm_id}...")
                        status = ATMLiveStatus(ATMId=atm_id, IsOnline=True)
                        live_status_repo.save(status)
                        session.flush()
                        
                    original_version = status.RowVersion
                    
                    # Concurrency conflict simulation hook
                    if self._simulate_concurrency_conflict and attempt_idx == 0:
                        original_version = b'\x00\x00\x00\x00\x00\x00\x00\x00'

                    # Timestamp Protection: ignore status update if a newer event exists
                    if status.LastEventTime is not None and status.LastEventTime > ev.EventTime:
                        # Skip live status update fields but proceed to commit historical ATMEvent
                        concurrency_success = True
                        break
                        
                    # Apply changes to live status record
                    self._apply_status_updates(status, ev, matching_snaps)
                    
                    # Optimistic update
                    updated = live_status_repo.update_live_status(status, original_version)
                    if updated:
                        concurrency_success = True
                        stats.LiveStatusUpdates += 1
                        break
                    else:
                        agent_logger.info("Concurrency Retry")
                        stats.DatabaseRetries += 1
                        # Continue loop to reload and retry once
                        
                if not concurrency_success:
                    raise Exception(f"Failed to update live status on ATM ID {atm_id} due to optimistic concurrency lock.")

                # Commit Transaction
                session.commit()
                agent_logger.info("Transaction Committed")

            except Exception as e:
                try:
                    session.rollback()
                    agent_logger.warning("Transaction Rolled Back")
                except Exception:
                    pass
                
                # Log error to AgentHealthLog autonomously
                self._log_health_error(atm_id, ev.EventSequenceNumber, e)
                stats.HealthLogsWritten += 1

            finally:
                session.close()

        end_time = time.perf_counter()
        stats.ProcessingTimeMs = (end_time - start_time) * 1000.0
        
        agent_logger.info("Processing Finished")
        agent_logger.info(f"Rows Inserted: {stats.EventsInserted + stats.CassetteSnapshotsInserted}")
        agent_logger.info(f"Rows Updated: {stats.LiveStatusUpdates}")
        agent_logger.info(f"Processing Duration (ms): {stats.ProcessingTimeMs:.2f}")
        
        return stats

    def _apply_status_updates(self, status: ATMLiveStatus, ev: ATMParsedEvent, snaps: List[CassetteSnapshot]) -> None:
        """Applies parsed operational attributes to ATMLiveStatus without writing to DB."""
        if ev.TerminalStatus is not None:
            status.CurrentStatus = ev.TerminalStatus
            status.SSTStatus = ev.TerminalStatus
            if ev.TerminalStatus in ["InService", "Online"]:
                status.IsOnline = True
            elif ev.TerminalStatus in ["OutOfService", "Offline"]:
                status.IsOnline = False

        if ev.SupervisorMode is not None:
            status.SupervisorMode = ev.SupervisorMode

        status.LastAgentHeartbeat = datetime.datetime.now()
        status.LastEventType = ev.EventType
        status.LastEventTime = ev.EventTime

        # Transaction details
        if ev.Amount is not None:
            status.LastTransactionTime = ev.EventTime
            status.LastTransactionAmount = ev.Amount

        # Card Reader Status
        if ev.EventType == "CardReaderActivated":
            status.CardReaderStatus = "Normal"
        elif ev.IsCardCaptured:
            status.CardReaderStatus = "Normal"

        # Reject Bin Status
        if ev.IsRejectBinRemoved:
            status.RejectBinStatus = "Missing"
        elif ev.IsRejectBinInserted:
            status.RejectBinStatus = "Normal"

        # Update Cassette details from snapshots
        for snap in snaps:
            c_no = snap.CassetteNo
            if c_no == 1:
                status.Cassette1Status = snap.CassetteStatus
                if snap.RemainingNotes is not None:
                    status.Cassette1RemainingNotes = snap.RemainingNotes
            elif c_no == 2:
                status.Cassette2Status = snap.CassetteStatus
                if snap.RemainingNotes is not None:
                    status.Cassette2RemainingNotes = snap.RemainingNotes
            elif c_no == 3:
                status.Cassette3Status = snap.CassetteStatus
                if snap.RemainingNotes is not None:
                    status.Cassette3RemainingNotes = snap.RemainingNotes
            elif c_no == 4:
                status.Cassette4Status = snap.CassetteStatus
                if snap.RemainingNotes is not None:
                    status.Cassette4RemainingNotes = snap.RemainingNotes

        # Calculate cash counts
        total_rem = 0
        rem_count_valid = False
        
        c_counts = [
            status.Cassette1RemainingNotes,
            status.Cassette2RemainingNotes,
            status.Cassette3RemainingNotes,
            status.Cassette4RemainingNotes
        ]
        
        for cnt in c_counts:
            if cnt is not None:
                total_rem += cnt
                rem_count_valid = True
                
        c_denoms = {1: 1000, 2: 500, 3: 100, 4: 50}
        for snap in snaps:
            if snap.Denomination is not None:
                c_denoms[snap.CassetteNo] = snap.Denomination

        calc_cash = 0.0
        for i, cnt in enumerate(c_counts):
            c_no = i + 1
            if cnt is not None:
                calc_cash += cnt * c_denoms.get(c_no, 0)
                
        if rem_count_valid:
            status.TotalRemainingNotes = total_rem
            status.CashRemainingAmount = calc_cash
            status.CashAvailable = (total_rem > 0)

        status.LastHeartbeat = ev.EventTime

    def _log_health_error(self, atm_id: int, sequence_number: Optional[int], exception: Exception) -> None:
        """Inserts an error record to AgentHealthLog in a new autonomous database connection."""
        health_session = self.session_factory()
        try:
            health_session.begin()
            health_repo = HealthRepository(health_session)
            
            error_log = AgentHealthLog(
                ATMId=atm_id,
                LogTime=datetime.datetime.now(),
                Level="Error",
                EventType="DatabaseError",
                Message=f"Database transaction failure on sequence {sequence_number}",
                ExceptionDetails=str(exception),
                SourceFileName="event_processor_service.py"
            )
            health_repo.insert_log(error_log)
            health_session.commit()
            agent_logger.info(f"Logged transaction failure to AgentHealthLog for sequence {sequence_number}.")
        except Exception as he:
            try:
                health_session.rollback()
            except Exception:
                pass
            agent_logger.error(f"Failed to log database error to AgentHealthLog: {he}")
        finally:
            health_session.close()
