"""
Centralized runtime path resolution for the ATM Monitoring Agent.

This module is the ONLY source of truth for resolving runtime directories.
It correctly handles both normal Python execution and PyInstaller frozen executables.

When running as a frozen PyInstaller executable:
    - sys.frozen is True
    - sys.executable points to the .exe file
    - All runtime paths are resolved relative to the executable's directory

When running from source (development):
    - sys.frozen is not set
    - All runtime paths are resolved relative to the project's agent/ directory
"""

import sys
import os


def get_application_dir() -> str:
    """
    Returns the root application directory.

    Frozen (PyInstaller):  directory containing the .exe
    Development:           the 'agent/' directory (parent of utils/)
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        # utils/paths.py -> utils/ -> agent/
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_log_dir() -> str:
    """Returns the directory for application log files. Creates it if missing."""
    log_dir = os.path.join(get_application_dir(), "logs")
    os.makedirs(log_dir, exist_ok=True)
    return log_dir


def get_crash_dir() -> str:
    """Returns the directory for crash dump files. Creates it if missing."""
    crash_dir = os.path.join(get_application_dir(), "crash")
    os.makedirs(crash_dir, exist_ok=True)
    return crash_dir


def get_config_dir() -> str:
    """Returns the directory where configuration files (.env) are located."""
    return get_application_dir()


def get_diagnostics_dir() -> str:
    """Returns the directory for diagnostics.json output."""
    return get_application_dir()


def get_log_file_path(filename: str = "agent.log") -> str:
    """Returns the full path for a log file inside the logs directory."""
    return os.path.join(get_log_dir(), filename)


def get_crash_file_path(filename: str) -> str:
    """Returns the full path for a crash dump file inside the crash directory."""
    return os.path.join(get_crash_dir(), filename)


def get_diagnostics_file_path(filename: str = "diagnostics.json") -> str:
    """Returns the full path for the diagnostics snapshot file."""
    return os.path.join(get_diagnostics_dir(), filename)


def get_env_file_path() -> str:
    """
    Returns the path to the .env configuration file.
    
    Search order:
        1. Application directory (beside the .exe or agent/ root)
        2. Parent of application directory (legacy layout)
    
    Returns the first path that exists, or the application directory path
    as the default even if the file does not exist yet.
    """
    app_dir = get_application_dir()
    
    primary = os.path.join(app_dir, ".env")
    if os.path.exists(primary):
        return primary
    
    parent = os.path.join(os.path.dirname(app_dir), ".env")
    if os.path.exists(parent):
        return parent
    
    # Default: application directory (file may not exist yet)
    return primary


def is_frozen() -> bool:
    """Returns True if running inside a PyInstaller frozen executable."""
    return getattr(sys, 'frozen', False)


def bootstrap_directories() -> None:
    """
    Ensures all writable runtime directories exist.
    Called once at agent startup.
    """
    get_log_dir()
    get_crash_dir()
