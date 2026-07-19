import os
import datetime
import time
import sqlalchemy.exc
import pyodbc
from sqlalchemy.orm import Session
from database.models import AgentFileState, ATM
from repositories.agent_repository import AgentRepository
from repositories.atm_repository import ATMRepository
from parsers.ej_parser import EJParser
from services.event_processor_service import EventProcessorService
from utils.logger import agent_logger, log_windows_event
from utils.file_utils import calculate_file_hash, read_appended_lines
from utils.circuit_breaker import CircuitBreaker
from utils.metrics import metrics_tracker

class ParserService:
    def __init__(self, session_factory, backoff_delays=None):
        self.session_factory = session_factory
        self.parser = EJParser()
        self.processor = EventProcessorService(session_factory)
        self.backoff_delays = backoff_delays if backoff_delays is not None else [5, 10, 20, 40, 60]
        self.circuit_breaker = CircuitBreaker(failure_threshold=5, cooldown_seconds=30.0)
        self._simulate_db_error = False
        self._simulate_db_error_count = 0
        self._simulate_transaction_error = False

    def process_file(self, atm_id: int, file_path: str) -> bool:
        """
        Reads newly appended lines from the log file, parses them, 
        and updates the AgentFileState in the database.
        Returns True if new data was parsed successfully, False otherwise.
        """
        # Circuit Breaker check
        if not self.circuit_breaker.can_execute():
            agent_logger.debug("Circuit breaker is OPEN. Skipping database interaction.")
            return False

        if not os.path.exists(file_path):
            agent_logger.warning(f"EJ Log file not found at: '{file_path}'. Skipping scan.")
            return False

        attempt = 0
        
        while True:
            # Test hook simulation for database connection loss
            if self._simulate_db_error and self._simulate_db_error_count > 0:
                self._simulate_db_error_count -= 1
                db_err = sqlalchemy.exc.OperationalError("Simulated SQL Server connection loss", None, None)
                metrics_tracker.record_db_failure()
                self.circuit_breaker.record_failure()
                
                # Check if breaker opened
                if not self.circuit_breaker.can_execute():
                    agent_logger.warning("Circuit breaker opened during simulated connection retry. Aborting loop.")
                    return False
                    
                attempt += 1
                delay = self.backoff_delays[min(attempt - 1, len(self.backoff_delays) - 1)]
                agent_logger.warning(
                    f"SQL Retry Started. Retry Attempt Number {attempt}. "
                    f"Current Backoff Delay {delay} seconds. Error: {db_err}"
                )
                log_windows_event(
                    f"SQL Retry Started. Retry Attempt Number {attempt}. Delay {delay}s. Error: {db_err}",
                    level="WARNING"
                )
                metrics_tracker.record_retry()
                metrics_tracker.record_reconnect()
                metrics_tracker.set_retry_state(True)
                time.sleep(delay)
                continue

            session = self.session_factory()
            try:
                # 1. Start implicit transaction scope for file state check
                session.begin()
                
                agent_repo = AgentRepository(session)
                atm_repo = ATMRepository(session)

                # Load or create AgentFileState
                state = agent_repo.get_file_state(atm_id, file_path)
                file_name = os.path.basename(file_path)
                file_size = os.path.getsize(file_path)
                modified_time = datetime.datetime.fromtimestamp(os.path.getmtime(file_path))
                
                # Determine prefix length to compute header hash
                prefix_len = 8192
                if state and state.LastReadOffset > 0:
                    prefix_len = min(8192, state.LastReadOffset)
                    
                header_hash = self._get_header_hash(file_path, prefix_len)

                if not state:
                    agent_logger.info(f"Initializing new AgentFileState for '{file_path}'...")
                    state = AgentFileState(
                        ATMId=atm_id,
                        FilePath=file_path,
                        FileName=file_name,
                        LastFileSize=file_size,
                        LastReadOffset=0,
                        LastModifiedTime=modified_time,
                        FileHash=header_hash,
                        IsActive=True
                    )
                    agent_repo.create_file_state(state)
                    session.flush()

                # 2. Rotation / Truncation Detection
                rotation_detected = False
                
                # Case A: File size shrunk below last read offset
                if file_size < state.LastReadOffset:
                    agent_logger.warning(f"Log truncation detected on '{file_path}' (Size: {file_size} < Offset: {state.LastReadOffset}). Resetting offset.")
                    rotation_detected = True
                
                # Case B: Header hash changed (file replaced with another)
                elif state.FileHash and header_hash != state.FileHash:
                    agent_logger.warning(f"Log rotation/replacement detected on '{file_path}' (Hash changed). Resetting offset.")
                    rotation_detected = True

                if rotation_detected:
                    state.LastReadOffset = 0
                    prefix_len = 8192
                    header_hash = self._get_header_hash(file_path, prefix_len)
                    state.FileHash = header_hash
                    agent_logger.info("Offset reset successfully.")

                # 3. Check if there are new bytes to read
                if file_size == state.LastReadOffset:
                    session.commit()
                    agent_logger.info("Transaction Committed")
                    self._record_reconnect_success(attempt)
                    
                    self.circuit_breaker.record_success()
                    metrics_tracker.record_scan(0.001, 0, state.LastReadOffset)
                    return False

                # 4. Read newly appended bytes safely
                scan_start = time.perf_counter()
                lines, new_offset, current_size = read_appended_lines(file_path, state.LastReadOffset)
                scan_duration = time.perf_counter() - scan_start
                bytes_read = new_offset - state.LastReadOffset
                
                if not lines:
                    session.commit()
                    agent_logger.info("Transaction Committed")
                    self._record_reconnect_success(attempt)
                    
                    self.circuit_breaker.record_success()
                    metrics_tracker.record_scan(scan_duration, 0, state.LastReadOffset)
                    return False

                # 5. Parse log lines
                parse_start = time.perf_counter()
                result = self.parser.parse_lines(lines, file_name=file_name)
                parse_duration = time.perf_counter() - parse_start

                # 6. Print concise summary
                stats = result.statistics
                coverage_pct = 100.0
                total_events_warnings = stats.ParsedEvents + stats.Warnings
                if total_events_warnings > 0:
                    coverage_pct = (stats.ParsedEvents / total_events_warnings) * 100.0

                print("\n" + "=" * 50)
                print("PARSER EXECUTION SUMMARY:")
                print(f"New Events:         {stats.ParsedEvents}")
                print(f"Cassette Snapshots: {stats.CassetteSnapshots}")
                print(f"Warnings:           {stats.Warnings}")
                print(f"Coverage:           {coverage_pct:.1f}%")
                print("=" * 50 + "\n")

                # 6b. Persist parsed events and status updates to SQL Server
                commit_start = time.perf_counter()
                self.processor.process_result(atm_id, result)

                # Test hook to simulate transaction error
                if self._simulate_transaction_error:
                    self._simulate_transaction_error = False
                    raise Exception("Simulated transaction rollback error")

                # 7. Update AgentFileState on successful parse completion
                state.LastReadOffset = new_offset
                state.LastFileSize = file_size
                state.LastModifiedTime = modified_time
                state.FileHash = self._get_header_hash(file_path, min(8192, new_offset))
                state.UpdatedOn = datetime.datetime.now()
                
                # Extract last sequence and event time if events were parsed
                if result.events:
                    last_event = result.events[-1]
                    state.LastParsedEventTime = last_event.EventTime
                    if last_event.EventSequenceNumber is not None:
                        state.LastSequenceNumber = last_event.EventSequenceNumber

                agent_repo.update_file_state(state)
                session.commit()
                commit_duration = time.perf_counter() - commit_start
                agent_logger.info("Transaction Committed")
                
                self._record_reconnect_success(attempt)
                
                # Record metrics
                metrics_tracker.record_scan(scan_duration, bytes_read, new_offset)
                metrics_tracker.record_parse(parse_duration)
                metrics_tracker.record_commit(commit_duration, len(result.events))
                
                # Record circuit success
                self.circuit_breaker.record_success()
                return True

            except (sqlalchemy.exc.OperationalError, sqlalchemy.exc.DBAPIError, sqlalchemy.exc.InterfaceError, pyodbc.Error) as db_err:
                try:
                    session.rollback()
                    agent_logger.warning("Transaction Rolled Back")
                except Exception:
                    pass
                
                metrics_tracker.record_db_failure()
                self.circuit_breaker.record_failure()
                
                # Check if breaker opened
                if not self.circuit_breaker.can_execute():
                    agent_logger.warning("Circuit breaker opened. Aborting retry loop.")
                    metrics_tracker.set_retry_state(False)
                    return False

                attempt += 1
                delay = self.backoff_delays[min(attempt - 1, len(self.backoff_delays) - 1)]
                agent_logger.warning(
                    f"SQL Retry Started. Retry Attempt Number {attempt}. "
                    f"Current Backoff Delay {delay} seconds. Error: {db_err}"
                )
                log_windows_event(
                    f"SQL Retry Started. Retry Attempt Number {attempt}. Delay {delay}s. Error: {db_err}",
                    level="WARNING"
                )
                metrics_tracker.record_retry()
                metrics_tracker.record_reconnect()
                metrics_tracker.set_retry_state(True)
                time.sleep(delay)
                continue

            except Exception as e:
                try:
                    session.rollback()
                    agent_logger.warning("Transaction Rolled Back")
                except Exception:
                    pass
                metrics_tracker.record_parser_failure()
                agent_logger.exception(f"Error processing log file '{file_path}': {e}")
                log_windows_event(f"Parser Failure: {e}", level="ERROR")
                metrics_tracker.set_retry_state(False)
                raise e
            finally:
                session.close()

    def _get_header_hash(self, file_path: str, prefix_len: int = 8192) -> str:
        """Helper to get hash of first prefix_len bytes of the file for rotation check."""
        if not os.path.exists(file_path):
            return ""
        try:
            with open(file_path, "rb") as f:
                content = f.read(prefix_len)
            import hashlib
            return hashlib.sha256(content).hexdigest()
        except Exception:
            return ""

    def _record_reconnect_success(self, attempt):
        if attempt > 0:
            agent_logger.info("Database Connection Restored")
            log_windows_event("Database Connection Restored successfully.", level="INFO")
            metrics_tracker.set_retry_state(False)
            metrics_tracker.record_successful_connection()
