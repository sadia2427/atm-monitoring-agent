import sys
import os
import traceback
from datetime import datetime
from version import get_version_info
from utils.logger import agent_logger, log_windows_event
from utils.metrics import metrics_tracker

def global_exception_handler(exctype, value, tb):
    """Global unhandled exception hook to generate structured crash dump."""
    crash_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tb_lines = traceback.format_exception(exctype, value, tb)
    tb_text = "".join(tb_lines)
    
    try:
        from config import config
        version_info = get_version_info(terminal_id=config.atm_terminal_id)
    except Exception:
        version_info = {
            "TerminalId": "UNKNOWN",
            "AgentVersion": "1.0.0",
            "BuildNumber": "1042",
            "PythonVersion": sys.version.split()[0],
            "OS": "Windows",
            "Hostname": "localhost"
        }
        
    health_metrics = metrics_tracker.get_health_metrics()
    
    crash_report = f"""====================================================
CRASH DUMP REPORT - {crash_time}
====================================================
Exception Type:     {exctype.__name__}
Exception Message:  {value}
ATM TerminalId:     {version_info['TerminalId']}
Agent Version:      {version_info['AgentVersion']}
Build Number:       {version_info['BuildNumber']}
Python Version:     {version_info['PythonVersion']}
OS Version:         {version_info['OS']}
Hostname:           {version_info['Hostname']}

----------------------------------------------------
RUNTIME METRICS SNAPSHOT
----------------------------------------------------
Uptime (Seconds):   {health_metrics['AgentUptime']}
Files Processed:    {health_metrics['FilesProcessed']}
Bytes Read:         {health_metrics['BytesRead']}
Events Persisted:   {health_metrics['EventsPersisted']}
Database Failures:  {health_metrics['DatabaseFailures']}
Parser Failures:    {health_metrics['ParserFailures']}
Current Offset:     {health_metrics['CurrentOffset']}

----------------------------------------------------
STACK TRACE
----------------------------------------------------
{tb_text}
"""
    # Write to Windows Event Log
    log_windows_event(f"ATMAgent crashed with unhandled exception: {value}", level="ERROR")
    
    # Save to dedicated crash log file
    try:
        from utils.paths import get_crash_file_path
        crash_file = get_crash_file_path(f"crash_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
        with open(crash_file, "w", encoding="utf-8") as f:
            f.write(crash_report)
        agent_logger.critical(f"FATAL: Unhandled exception occurred. Crash dump written to '{crash_file}'")
    except Exception as e:
        print(f"Error writing crash report: {e}", file=sys.stderr)
        
    # Call standard handler
    sys.__excepthook__(exctype, value, tb)

def register_crash_handler():
    sys.excepthook = global_exception_handler
