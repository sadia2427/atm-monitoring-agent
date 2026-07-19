import logging
from logging.handlers import RotatingFileHandler
import os
import sys

def log_windows_event(message: str, level: str = "INFO"):
    """Logs events directly to the Windows Event Log (NT Event Log) if win32evtlog is available."""
    try:
        import win32evtlogutil
        import win32evtlog
        event_type = win32evtlog.EVENTLOG_INFORMATION_TYPE
        event_id = 1001
        
        lvl_upper = level.upper()
        if lvl_upper == "WARNING":
            event_type = win32evtlog.EVENTLOG_WARNING_TYPE
            event_id = 1002
        elif lvl_upper == "ERROR":
            event_type = win32evtlog.EVENTLOG_ERROR_TYPE
            event_id = 1003
        
        win32evtlogutil.ReportEvent(
            "ATMAgent",
            event_id,
            eventType=event_type,
            strings=[message]
        )
    except Exception:
        # Ignore silently if pywin32 is not installed or EventLog is inaccessible
        pass

def setup_logger(name: str = "ATMAgent", log_file: str = "agent.log", max_bytes: int = 10 * 1024 * 1024, backup_count: int = 5) -> logging.Logger:
    """Configures and returns a structured logging instance with log rotation."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    if logger.handlers:
        return logger
        
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # 1. Console Output Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 2. Rotating File Output Handler
    try:
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
            
        file_handler = RotatingFileHandler(
            log_file, 
            maxBytes=max_bytes, 
            backupCount=backup_count, 
            encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"Warning: Could not configure file logger: {e}", file=sys.stderr)
        
    return logger

# Determine log file path in the agent directory
agent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
log_file_path = os.path.join(agent_dir, "agent.log")

# Instantiate default logger
agent_logger = setup_logger(log_file=log_file_path)
