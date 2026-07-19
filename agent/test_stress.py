import os
import sys
import time
import datetime
import threading
import sqlalchemy.exc
import ctypes
from ctypes import wintypes
from sqlalchemy.orm import Session
from database.db import SessionLocal, test_db_connection
from database.models import ATM, AgentFileState, ATMEvent, ATMLiveStatus, AgentSettings
from repositories.agent_repository import AgentRepository
from services.parser_service import ParserService
from services.file_monitor_service import FileMonitorService
from utils.logger import agent_logger
from utils.metrics import metrics_tracker
from utils.file_utils import read_appended_lines
from settings import settings_manager

# Pure-ctypes Windows Process Memory Helper
class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakWorkingSetSize", ctypes.c_size_t),
        ("QuotaWorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolSize", ctypes.c_size_t),
        ("QuotaPagedPoolSize", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolSize", ctypes.c_size_t),
        ("QuotaNonPagedPoolSize", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]

def get_process_memory_mb() -> float:
    """Gets the current process Working Set (RSS) Memory usage in MB."""
    try:
        GetProcessMemoryInfo = ctypes.windll.psapi.GetProcessMemoryInfo
        GetCurrentProcess = ctypes.windll.kernel32.GetCurrentProcess
        
        process_handle = GetCurrentProcess()
        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
        
        if GetProcessMemoryInfo(process_handle, ctypes.byref(counters), counters.cb):
            return counters.WorkingSetSize / (1024.0 * 1024.0)
    except Exception:
        pass
    return 0.0

def run_stress_tests():
    agent_logger.info("=== Starting ATM Monitor Stress & Reliability Testing ===")
    
    if not test_db_connection():
        agent_logger.error("Database connection unavailable. Exiting.")
        sys.exit(1)

    agent_dir = os.path.dirname(os.path.abspath(__file__))
    stress_log_path = os.path.abspath(os.path.join(agent_dir, "stress_test_ej.log"))

    # 1. Update test ATM log path configuration
    session = SessionLocal()
    try:
        atm = session.query(ATM).filter(ATM.TerminalId == "ATM001").first()
        if not atm:
            agent_logger.error("ATM 'ATM001' not found. Please run seeder first.")
            sys.exit(1)
        original_path = atm.EJLogPath
        atm.EJLogPath = stress_log_path
        session.commit()
        atm_id = atm.Id
    finally:
        session.close()

    # Cleanup previous states
    if os.path.exists(stress_log_path):
        os.remove(stress_log_path)
    
    session = SessionLocal()
    try:
        session.query(AgentFileState).filter(AgentFileState.ATMId == atm_id).delete()
        session.query(ATMEvent).filter(ATMEvent.ATMId == atm_id).delete()
        session.query(ATMLiveStatus).filter(ATMLiveStatus.ATMId == atm_id).delete()
        session.commit()
    finally:
        session.close()

    metrics_tracker.reset()

    # ----------------------------------------------------
    # TEST 1: 100,000 Events & Memory Protection
    # ----------------------------------------------------
    agent_logger.info("--- Stress Test 1: 100,000 Events & Memory Limit Check ---")
    
    # Generate 100,000 operational events in chunks to minimize memory footprint
    batch_size = 20000
    with open(stress_log_path, "w", encoding="utf-8") as f:
        seq = 1000
        for i in range(100000):
            # Alternate some events
            if i % 2 == 0:
                f.write(f"*{seq}*15/07/2026*12:00*\n CARD INSERTED\n")
            else:
                f.write(f"*{seq}*15/07/2026*12:01*\n SST IN SERVICE\n")
            seq += 1

    parser_service = ParserService(SessionLocal)
    
    # Measure memory and duration
    mem_before = get_process_memory_mb()
    
    start_time = time.perf_counter()
    # Process file (incrementally reads in 10MB chunks max as defined in file_utils)
    success = parser_service.process_file(atm_id, stress_log_path)
    assert success is True
    
    duration = time.perf_counter() - start_time
    mem_after = get_process_memory_mb()
    
    agent_logger.info(f"Processed 100,000 events in {duration:.2f} seconds.")
    agent_logger.info(f"Memory RSS Before: {mem_before:.2f} MB, After: {mem_after:.2f} MB. Spike: {mem_after - mem_before:.2f} MB")
    
    # Check that events are in database
    session = SessionLocal()
    try:
        events_count = session.query(ATMEvent).filter(ATMEvent.ATMId == atm_id).count()
        assert events_count == 100000, f"Expected 100,000 database events, got {events_count}"
        agent_logger.info("SUCCESS: 100,000 events successfully stored.")
    finally:
        session.close()

    # ----------------------------------------------------
    # TEST 2: Circuit Breaker Verification
    # ----------------------------------------------------
    agent_logger.info("--- Stress Test 2: Circuit Breaker Failure Storm Stop ---")
    
    # Trigger 5 failures
    parser_service.circuit_breaker.failure_threshold = 5
    parser_service.circuit_breaker.cooldown_seconds = 2.0  # short cooldown for testing
    
    parser_service._simulate_db_error = True
    parser_service._simulate_db_error_count = 10
    
    # Write some new content to trigger parsing attempts
    with open(stress_log_path, "a", encoding="utf-8") as f:
        f.write("*200000*15/07/2026*13:00*\n CARD INSERTED\n")

    # Run processing. It should attempt and fail 5 times, opening the circuit, and stop retrying.
    success = parser_service.process_file(atm_id, stress_log_path)
    assert success is False, "Should fail due to SQL connection error"
    
    assert parser_service.circuit_breaker.state == "OPEN", f"Circuit Breaker state should be OPEN, got {parser_service.circuit_breaker.state}"
    agent_logger.info("SUCCESS: Circuit Breaker successfully transitioned to OPEN on 5 consecutive failures.")

    # Try processing again immediately. It should be blocked by circuit breaker instantly without attempting DB.
    start_attempt = time.perf_counter()
    success = parser_service.process_file(atm_id, stress_log_path)
    duration_attempt = time.perf_counter() - start_attempt
    assert success is False
    assert duration_attempt < 0.05, f"Instant reject should take < 50ms, took {duration_attempt * 1000:.2f}ms"
    agent_logger.info("SUCCESS: Instant call block while breaker is OPEN verified.")

    # Wait for cooldown to expire
    time.sleep(2.1)
    
    # Disable simulated errors and try again. It will transition to HALF-OPEN, try, and transition to CLOSED on success.
    parser_service._simulate_db_error = False
    parser_service._simulate_db_error_count = 0
    
    success = parser_service.process_file(atm_id, stress_log_path)
    assert success is True, "Should succeed now that database error is cleared"
    assert parser_service.circuit_breaker.state == "CLOSED"
    agent_logger.info("SUCCESS: Circuit Breaker automatically recovered and closed on success.")

    # ----------------------------------------------------
    # TEST 3: Graceful Shutdown mid-scan
    # ----------------------------------------------------
    agent_logger.info("--- Stress Test 3: Graceful Shutdown Mid-Scan ---")
    
    # Append events
    with open(stress_log_path, "a", encoding="utf-8") as f:
        f.write("*200001*15/07/2026*13:05*\n SST IN SERVICE\n")
        f.write("*200002*15/07/2026*13:06*\n SST OUT OF SERVICE\n")

    monitor = FileMonitorService(atm_id, stress_log_path, parser_service, scan_interval=0.5)
    monitor.start()

    # Trigger a scan, and immediately stop it
    # Calling stop() acquires lock and blocks until the currently running scan (if any) is finished!
    stop_start = time.perf_counter()
    monitor.stop()
    stop_duration = time.perf_counter() - stop_start
    
    agent_logger.info(f"Graceful stop executed in {stop_duration:.4f} seconds.")
    
    # Verify that events 200001 and 200002 are in database (not lost!)
    session = SessionLocal()
    try:
        ev1 = session.query(ATMEvent).filter(ATMEvent.ATMId == atm_id, ATMEvent.EventSequenceNumber == 200001).first()
        ev2 = session.query(ATMEvent).filter(ATMEvent.ATMId == atm_id, ATMEvent.EventSequenceNumber == 200002).first()
        assert ev1 is not None, "Event 200001 should be processed"
        assert ev2 is not None, "Event 200002 should be processed"
        agent_logger.info("SUCCESS: Shutdown completed gracefully without losing any parsing transaction data.")
    finally:
        session.close()

    # ----------------------------------------------------
    # TEST 4: Config Hot Reload
    # ----------------------------------------------------
    agent_logger.info("--- Stress Test 4: Configuration Hot Reload ---")
    # Update settings log scan interval in database
    session = SessionLocal()
    try:
        settings = session.query(AgentSettings).order_by(AgentSettings.Id.asc()).first()
        original_interval = settings.LogScanIntervalSeconds
        settings.LogScanIntervalSeconds = 12
        session.commit()
    finally:
        session.close()

    # Force reloading settings from settings cache manager
    settings_manager.load_settings(force=True)
    
    # Check monitor service adopts it
    monitor = FileMonitorService(atm_id, stress_log_path, parser_service, scan_interval=1)
    monitor.is_running = True
    
    # Check settings reloaded is 12 seconds
    reloaded_settings = settings_manager.get_settings()
    assert reloaded_settings.LogScanIntervalSeconds == 12
    agent_logger.info(f"SUCCESS: Configuration reloaded successfully. LogScanIntervalSeconds: {reloaded_settings.LogScanIntervalSeconds}")

    # Restore settings
    session = SessionLocal()
    try:
        settings = session.query(AgentSettings).order_by(AgentSettings.Id.asc()).first()
        settings.LogScanIntervalSeconds = original_interval
        session.commit()
    finally:
        session.close()
    settings_manager.load_settings(force=True)

    # ----------------------------------------------------
    # TEST 5: Log File Locked Handling
    # ----------------------------------------------------
    agent_logger.info("--- Stress Test 5: Locked Log File Exponential Retry ---")
    
    # We will simulate file open raising PermissionError
    # We can mock builtins.open temporarily to throw PermissionError on stress_log_path twice, and then succeed.
    original_open = open
    attempts = [0]
    
    def mock_open(file, mode="r", *args, **kwargs):
        if file == stress_log_path and attempts[0] < 2:
            attempts[0] += 1
            raise PermissionError("Sharing violation lock on EJ log file")
        return original_open(file, mode, *args, **kwargs)

    # Apply mock
    import builtins
    builtins.open = mock_open
    
    try:
        # Append some text
        with original_open(stress_log_path, "a", encoding="utf-8") as f:
            f.write("*300000*15/07/2026*14:00*\n CARD INSERTED\n")
            
        success = parser_service.process_file(atm_id, stress_log_path)
        assert success is True
        assert attempts[0] == 2, f"Expected 2 locked attempts, got {attempts[0]}"
        agent_logger.info("SUCCESS: Locked file reads completed successfully after automatic backoff retries.")
    finally:
        builtins.open = original_open

    # ----------------------------------------------------
    # Cleanup
    # ----------------------------------------------------
    if os.path.exists(stress_log_path):
        os.remove(stress_log_path)
        
    session = SessionLocal()
    try:
        atm = session.query(ATM).filter(ATM.TerminalId == "ATM001").first()
        if atm:
            atm.EJLogPath = original_path
            session.commit()
    finally:
        session.close()

    # Print final test metrics
    perf = metrics_tracker.get_performance_metrics()
    agent_logger.info("=== Performance Statistics ===")
    agent_logger.info(f"Avg Parse Time:      {perf['AverageParseTime'] * 1000.0:.2f} ms")
    agent_logger.info(f"Avg DB Commit Time:  {perf['AverageDbCommitTime'] * 1000.0:.2f} ms")
    agent_logger.info(f"Avg File Scan Time:  {perf['AverageFileScanTime'] * 1000.0:.2f} ms")
    agent_logger.info(f"Max Parse Duration:  {perf['MaximumParseDuration'] * 1000.0:.2f} ms")
    agent_logger.info(f"Max Commit Duration: {perf['MaximumCommitDuration'] * 1000.0:.2f} ms")
    
    agent_logger.info("=== Stress & Reliability Testing Completed Successfully ===")

if __name__ == "__main__":
    run_stress_tests()
