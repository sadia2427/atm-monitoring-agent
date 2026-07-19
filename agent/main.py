import os
import sys
import time
import signal
import datetime
import socket

# Ensure the agent root folder is in the Python load path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import config
from database.db import test_db_connection, SessionLocal
from database.models import ATM
from settings import settings_manager
from utils.logger import agent_logger, log_windows_event
from utils.crash_handler import register_crash_handler
from version import get_version_info
from services.parser_service import ParserService
from services.file_monitor_service import FileMonitorService
from services.heartbeat_service import HeartbeatService
from services.cleanup_service import CleanupService
from services.health_monitor_service import HealthMonitorService

# Global service references for signal handler access
monitor = None
heartbeat = None
cleanup = None
health_monitor = None
running = True

def handle_shutdown(signum, frame):
    global monitor, heartbeat, cleanup, health_monitor, running
    agent_logger.info(f"Signal received ({signum}). Initiating graceful shutdown...")
    log_windows_event("ATM Monitoring Agent Shutdown Initiated", level="INFO")
    running = False
    
    # 1. Stop health monitor first to avoid it trying to restart workers during shutdown
    if health_monitor:
        try:
            health_monitor.stop()
        except Exception as e:
            agent_logger.error(f"Error stopping health monitor: {e}")
            
    # 2. Stop file monitor
    if monitor:
        try:
            monitor.stop()
        except Exception as e:
            agent_logger.error(f"Error stopping file monitor: {e}")
            
    # 3. Stop heartbeat
    if heartbeat:
        try:
            heartbeat.stop()
        except Exception as e:
            agent_logger.error(f"Error stopping heartbeat: {e}")
            
    # 4. Stop cleanup
    if cleanup:
        try:
            cleanup.stop()
        except Exception as e:
            agent_logger.error(f"Error stopping cleanup: {e}")
            
    agent_logger.info("Graceful shutdown completed. Exiting.")
    log_windows_event("ATM Monitoring Agent Stopped Gracefully", level="INFO")
    sys.exit(0)

def main():
    global monitor, heartbeat, cleanup, health_monitor, running
    
    # 1. Register global unhandled exception hook
    register_crash_handler()
    
    # 2. Register signal handlers for SIGINT (Ctrl+C) and SIGTERM
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)
    
    # 3. Log agent starting event
    log_windows_event("ATM Monitoring Agent Starting", level="INFO")
    agent_logger.info("=== ATM Monitoring Agent Initializing ===")
    
    # Validate database connection (Exit Code 1)
    agent_logger.info("Verifying SQL Server database connection...")
    if not test_db_connection():
        msg = "Startup validation failed: Database connection is unavailable."
        agent_logger.error(msg)
        log_windows_event(msg, level="ERROR")
        sys.exit(1)
    agent_logger.info("Database connection verified successfully.")
    log_windows_event("Database connection verified successfully.", level="INFO")

    session = SessionLocal()
    try:
        # Validate ATM exists (Exit Code 2)
        term_id = config.atm_terminal_id
        agent_logger.info(f"Querying ATM metadata for TerminalId: '{term_id}'...")
        atm = session.query(ATM).filter(ATM.TerminalId == term_id).first()
        if not atm:
            msg = f"Startup validation failed: ATM record with TerminalId '{term_id}' not found."
            agent_logger.error(msg)
            log_windows_event(msg, level="ERROR")
            sys.exit(2)
            
        # Validate AgentSettings exists (Exit Code 4)
        agent_logger.info("Loading AgentSettings from database...")
        settings = settings_manager.get_settings()
        if not settings:
            msg = "Startup validation failed: Active AgentSettings could not be loaded."
            agent_logger.error(msg)
            log_windows_event(msg, level="ERROR")
            sys.exit(4)
            
        # Validate EJ Log Path exists (Exit Code 3)
        log_path = atm.EJLogPath if atm.EJLogPath else settings.EJLogPath
        agent_logger.info(f"Validating EJ log path: '{log_path}'...")
        if not log_path or not os.path.exists(log_path):
            msg = f"Startup validation failed: EJ log path '{log_path}' does not exist."
            agent_logger.error(msg)
            log_windows_event(msg, level="ERROR")
            sys.exit(3)
            
        # 4. Generate startup environment and audit summary
        v_info = get_version_info(terminal_id=term_id)
        current_user = os.getenv("USERNAME") or os.getenv("USER") or "N/A"
        
        agent_dir = os.path.dirname(os.path.abspath(__file__))
        log_dir = agent_dir
        
        audit_summary = f"""
====================================================
ATM MONITOR MONITORING AGENT STARTUP AUDIT
====================================================
Agent Version:         {v_info['AgentVersion']}
Parser Version:        {v_info['ParserVersion']}
Build Number:          {v_info['BuildNumber']}
Build Date:            {v_info['BuildDate']}
Git Commit:            {v_info['GitCommit']}
Python Version:        {v_info['PythonVersion']}
OS/Platform:           {v_info['OS']}
Hostname:              {v_info['Hostname']}
Machine Name:          {v_info['MachineName']}
ATM TerminalId:        {term_id}
Database Server:       {config.db_server}
Database Name:         {config.db_database}
Current Log Path:      {log_path}
Configuration Version: {settings.Id}
Working Directory:     {os.getcwd()}
Log Directory:         {log_dir}
Current System User:   {current_user}
Startup Timestamp:     {v_info['StartupTimestamp']}
====================================================
"""
        agent_logger.info(audit_summary)
        print(audit_summary)
        
        log_windows_event(f"ATM Agent connected to database for ATM TerminalId '{term_id}'.", level="INFO")
        
        # 5. Initialize services
        parser_service = ParserService(SessionLocal)
        
        monitor = FileMonitorService(
            atm_id=atm.Id,
            file_path=log_path,
            parser_service=parser_service,
            scan_interval=settings.LogScanIntervalSeconds
        )
        
        heartbeat = HeartbeatService(
            atm_id=atm.Id,
            session_factory=SessionLocal,
            interval=settings.HeartbeatIntervalSeconds
        )
        
        cleanup = CleanupService(
            session_factory=SessionLocal,
            interval_seconds=86400  # Run daily database and file purge check
        )
        
        health_monitor = HealthMonitorService(
            monitor_service=monitor,
            heartbeat_service=heartbeat,
            max_restarts=5,
            check_interval=10
        )
        
        # Link references for dynamic diagnostics generation
        heartbeat.set_services(monitor, health_monitor)
        
        # 6. Start worker threads
        monitor.start()
        heartbeat.start()
        cleanup.start()
        health_monitor.start()
        
        # Keep main thread alive
        while running:
            time.sleep(1.0)
            
    except SystemExit as se:
        sys.exit(se.code)
    except Exception as e:
        agent_logger.exception(f"An unexpected error occurred during agent execution: {e}")
        log_windows_event(f"Unexpected Exception occurred: {e}", level="ERROR")
        sys.exit(5) # General exit code for unexpected initialization errors
    finally:
        session.close()

if __name__ == "__main__":
    main()
