# ATM Monitoring Agent

## Project Overview
The ATM Monitoring Agent is a high-performance, robust Windows application designed to monitor ATM Electronic Journal (EJ) logs in real-time. It streams, parses, and securely persists critical ATM operational events and hardware status telemetry to a centralized Microsoft SQL Server database. The agent is built to handle massive transactional loads while maintaining a tiny memory footprint.

## Architecture
The system employs a decentralized, file-monitoring daemon architecture:
*   **File Monitor Service:** Attaches via `watchdog` to the target ATM EJ Log and reads incrementally to avoid double ingestion.
*   **Parser Service:** Translates raw NCR format log lines into strongly-typed `ATMEvent` objects.
*   **Event Processor Service:** Manages transactional consistency, writing batches of events to SQL Server while handling optimistic concurrency for live status updates.
*   **Heartbeat & Health Monitor:** Ensures the agent remains alive, dynamically recovers from SQL Server or thread failures, and reports agent status to the database.

## Features
*   **Real-time Streaming:** Processes EJ log entries instantly as they are appended.
*   **Incremental Parsing:** Persists a `LastReadOffset` to safely resume processing without duplicating data after a service restart or host reboot.
*   **Crash Resilience:** Automatically recovers from disconnected databases, network drops, or internal thread crashes using a Circuit Breaker pattern.
*   **Cassette Cash Tracking:** Calculates and logs running cash totals and remaining notes based on snapshot data.
*   **Minimal Footprint:** Packaged as a standalone Windows executable (`onedir`) requiring no system-level Python installation. Peak memory remains below 100 MB.

## Folder Structure
The production distribution utilizes a single-folder paradigm (`onedir`):
```text
C:\Program Files\ATMAgent\
├── ATMAgent.exe          # Main application executable
├── _internal\            # Packaged Python runtime and dependencies
├── .env                  # Environment config (DB connections, TerminalId)
├── logs\                 # Rotating application execution logs
├── crash\                # Generated dumps on unhandled exceptions
└── diagnostics\          # Generated runtime snapshots on request or error
```

## Requirements
*   **Host OS:** Windows 10/11 or Windows Server (64-bit).
*   **Database:** Microsoft SQL Server (Express or Enterprise) 2019+.
*   **Driver:** Microsoft ODBC Driver 17 for SQL Server.

## Installation
1.  Ensure the SQL Server instance is reachable and the `ATMMonitoring` database exists.
2.  Copy the compiled `dist/ATMAgent` distribution to `C:\Program Files\ATMAgent\`.
3.  Ensure the executing service account has read access to the ATM's EJ Log file and write access to the agent's installation directory.

## Configuration
All application settings are injected via the `.env` file located beside `ATMAgent.exe`.
```env
# Database configuration
DB_SERVER=localhost\SQLEXPRESS
DB_DATABASE=ATMMonitoring
DB_USERNAME=
DB_PASSWORD=
DB_DRIVER=ODBC Driver 17 for SQL Server
DB_TRUSTED_CONNECTION=yes

# ATM Target Identification
ATM_TERMINAL_ID=ATM001
```
*Note: Advanced tuning (like polling intervals) is pulled securely from the `AgentSettings` table in the database.*

## Running the Agent
For manual execution and testing:
1.  Open an Administrator Command Prompt.
2.  Navigate to `C:\Program Files\ATMAgent\`.
3.  Execute `ATMAgent.exe`.

For production, configure the executable to run as a **Windows Service** (e.g., using NSSM).

## Logging
The agent maintains its own rolling logs inside the `logs\` directory. `agent.log` securely records agent operations, parsing summaries, and SQL latency metrics. Sensitive PAN data is immediately masked during the parse phase.

## Crash Recovery
The agent features a comprehensive `HealthMonitorService`. If a worker thread (such as the File Monitor) crashes, the agent will attempt to restart it up to 5 times. If SQL Server goes offline, the `CircuitBreaker` pauses ingestion and safely retries with backoff delays, ensuring zero data loss.

## Runtime Diagnostics
If the agent detects a severe failure (or is triggered manually), it generates a `diagnostics.json` file inside the `diagnostics\` directory. This snapshot includes thread locks, memory utilization, and the last known operational state.

## Packaging
The agent must be packaged using PyInstaller configured via the `agent.spec` file.
```cmd
pip install pyinstaller
pyinstaller agent.spec
```
This produces a `onedir` distribution which is heavily optimized for fast startup times on ATMs. **Do not use `--onefile`.**

## UAT
Refer to the `uat_checklist.md` document for the formal User Acceptance Testing sign-off procedures.

## Known Limitations
*   The agent currently expects NCR formatted EJ logs. Adding Diebold or Wincor support requires expanding the `ParserService` mapping rules.
*   Requires the ODBC 17 driver; older SQL drivers may reject `TrustServerCertificate` connection flags.

## Version History
*   **v1.0.0-rc1:** Initial Release Candidate. Feature freeze. MS SQL Server migration complete. Packaging abstraction implemented.
*   **v0.9.0:** Alpha release. SQLite backend. Initial parsing and monitoring implementations.
