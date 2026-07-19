import os
import sys
import json
import datetime
import socket
import ctypes
from ctypes import wintypes
from settings import settings_manager
from utils.metrics import metrics_tracker
from version import get_version_info
from database.db import test_db_connection

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

def get_peak_process_memory_mb() -> float:
    try:
        GetProcessMemoryInfo = ctypes.windll.psapi.GetProcessMemoryInfo
        GetCurrentProcess = ctypes.windll.kernel32.GetCurrentProcess
        process_handle = GetCurrentProcess()
        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
        if GetProcessMemoryInfo(process_handle, ctypes.byref(counters), counters.cb):
            return counters.PeakWorkingSetSize / (1024.0 * 1024.0)
    except Exception:
        pass
    return 0.0

def generate_diagnostics_snapshot(atm_id: int, file_path: str, parser_service, monitor_service, heartbeat_service, health_monitor_service):
    """Compiles configuration, thread statuses, and metrics into a local diagnostics.json file."""
    try:
        settings = settings_manager.get_settings()
        version_info = get_version_info()
        health_metrics = metrics_tracker.get_health_metrics()
        perf_metrics = metrics_tracker.get_performance_metrics()
        conn_diags = metrics_tracker.get_connection_diagnostics()
        
        thread_status = {
            "LogPollingThread": monitor_service.polling_thread.is_alive() if monitor_service and monitor_service.polling_thread else False,
            "WatchdogObserver": monitor_service.observer.is_alive() if monitor_service and monitor_service.observer else False,
            "HeartbeatThread": heartbeat_service.thread.is_alive() if heartbeat_service and heartbeat_service.thread else False,
            "HealthMonitorThread": health_monitor_service.thread.is_alive() if health_monitor_service and health_monitor_service.thread else False
        }
        
        snapshot = {
            "Timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "ATMId": atm_id,
            "TerminalId": version_info["TerminalId"],
            "AgentVersion": version_info["AgentVersion"],
            "ParserVersion": version_info["ParserVersion"],
            "WorkingSetMemoryMB": get_process_memory_mb(),
            "PeakWorkingSetMemoryMB": get_peak_process_memory_mb(),
            "DatabaseConnectivity": "CONNECTED" if test_db_connection() else "DISCONNECTED",
            "CircuitBreakerState": parser_service.circuit_breaker.state if parser_service else "CLOSED",
            "CurrentOffset": health_metrics["CurrentOffset"],
            "TargetLogFile": os.path.abspath(file_path),
            "Configuration": {
                "LogScanIntervalSeconds": settings.LogScanIntervalSeconds if settings else 2,
                "HeartbeatIntervalSeconds": settings.HeartbeatIntervalSeconds if settings else 30,
                "OfflineThresholdMinutes": settings.OfflineThresholdMinutes if settings else 60,
                "LowCashThresholdAmount": settings.LowCashThresholdAmount if settings else 500000,
                "RetentionDays": settings.RetentionDays if settings else 90
            },
            "ThreadStatuses": thread_status,
            "RuntimeMetrics": health_metrics,
            "PerformanceMetrics": perf_metrics,
            "ConnectionDiagnostics": conn_diags
        }
        
        # Datetime encoder for JSON
        def json_serial(obj):
            if isinstance(obj, (datetime.datetime, datetime.date)):
                return obj.strftime("%Y-%m-%d %H:%M:%S")
            raise TypeError("Type not serializable")
            
        agent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        snapshot_path = os.path.join(agent_dir, "diagnostics.json")
        
        with open(snapshot_path, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=4, default=json_serial)
    except Exception as e:
        from utils.logger import agent_logger
        agent_logger.error(f"Failed to generate diagnostics snapshot: {e}")
