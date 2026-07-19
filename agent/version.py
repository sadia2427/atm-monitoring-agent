import sys
import platform
import os
import socket
from datetime import datetime

AGENT_VERSION = "v1.0.0-rc1"
BUILD_NUMBER = "1042"
BUILD_DATE = "2026-07-19"
PARSER_VERSION = "2.1.0"
GIT_COMMIT = "a7b3c2d"

def get_git_commit():
    try:
        import subprocess
        # Get short git commit hash
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return GIT_COMMIT

def get_version_info(terminal_id: str = "ATM001") -> dict:
    return {
        "AgentVersion": AGENT_VERSION,
        "BuildNumber": BUILD_NUMBER,
        "BuildDate": BUILD_DATE,
        "ParserVersion": PARSER_VERSION,
        "GitCommit": get_git_commit(),
        "PythonVersion": sys.version.split()[0],
        "OS": f"{platform.system()} {platform.release()}",
        "MachineName": platform.machine(),
        "Hostname": socket.gethostname(),
        "TerminalId": terminal_id,
        "StartupTimestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
