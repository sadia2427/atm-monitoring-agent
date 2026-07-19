import time
import datetime
import threading

class MetricsTracker:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if not cls._instance:
                cls._instance = super(MetricsTracker, cls).__new__(cls, *args, **kwargs)
                cls._instance._init_metrics()
            return cls._instance

    def _init_metrics(self):
        self.lock = threading.Lock()
        self.start_time = datetime.datetime.now()
        
        # Health Metrics
        self.last_successful_parse = None
        self.last_database_write = None
        self.files_processed = 0
        self.bytes_read = 0
        self.events_persisted = 0
        self.database_failures = 0
        self.parser_failures = 0
        self.retries = 0
        self.current_offset = 0

        # Connection Pool Diagnostics
        self.reconnect_count = 0
        self.connection_failures = 0
        self.successful_connections = 0
        self.current_retry_state = False
        self.circuit_breaker_state = "CLOSED"
        self.pool_health = "HEALTHY"

        # Extended Runtime Diagnostics Metrics
        self.heartbeat_count = 0
        self.config_reload_count = 0
        self.cb_trips_count = 0
        self.parser_restart_count = 0
        self.worker_restart_count = 0
        self.peak_cpu_usage = 0.0

        # Performance Metrics
        self.parse_times = []
        self.commit_times = []
        self.scan_times = []
        self.max_parse_duration = 0.0
        self.max_commit_duration = 0.0

    def record_scan(self, scan_duration: float, bytes_read: int, offset: int):
        with self.lock:
            self.files_processed += 1
            self.bytes_read += bytes_read
            self.current_offset = offset
            self.scan_times.append(scan_duration)

    def record_parse(self, parse_duration: float):
        with self.lock:
            self.last_successful_parse = datetime.datetime.now()
            self.parse_times.append(parse_duration)
            if parse_duration > self.max_parse_duration:
                self.max_parse_duration = parse_duration

    def record_commit(self, commit_duration: float, events_count: int):
        with self.lock:
            self.last_database_write = datetime.datetime.now()
            self.events_persisted += events_count
            self.commit_times.append(commit_duration)
            if commit_duration > self.max_commit_duration:
                self.max_commit_duration = commit_duration

    def record_db_failure(self):
        with self.lock:
            self.database_failures += 1

    def record_parser_failure(self):
        with self.lock:
            self.parser_failures += 1

    def record_retry(self):
        with self.lock:
            self.retries += 1

    def record_reconnect(self):
        with self.lock:
            self.reconnect_count += 1
            
    def record_connection_failure(self):
        with self.lock:
            self.connection_failures += 1
            self.pool_health = "DEGRADED"
            
    def record_successful_connection(self):
        with self.lock:
            self.successful_connections += 1
            self.pool_health = "HEALTHY"
            
    def set_retry_state(self, retrying: bool):
        with self.lock:
            self.current_retry_state = retrying
            
    def set_circuit_breaker_state(self, state: str):
        with self.lock:
            self.circuit_breaker_state = state

    def record_heartbeat(self):
        with self.lock:
            self.heartbeat_count += 1

    def record_config_reload(self):
        with self.lock:
            self.config_reload_count += 1

    def record_cb_trip(self):
        with self.lock:
            self.cb_trips_count += 1

    def record_parser_restart(self):
        with self.lock:
            self.parser_restart_count += 1

    def record_worker_restart(self):
        with self.lock:
            self.worker_restart_count += 1

    def get_connection_diagnostics(self) -> dict:
        with self.lock:
            return {
                "ReconnectCount": self.reconnect_count,
                "ConnectionFailures": self.connection_failures,
                "SuccessfulConnections": self.successful_connections,
                "CurrentRetryState": "RETRYING" if self.current_retry_state else "NORMAL",
                "CircuitBreakerState": self.circuit_breaker_state,
                "PoolHealth": self.pool_health
            }

    def get_health_metrics(self) -> dict:
        with self.lock:
            uptime = (datetime.datetime.now() - self.start_time).total_seconds()
            return {
                "AgentUptime": uptime,
                "LastSuccessfulParse": self.last_successful_parse,
                "LastDatabaseWrite": self.last_database_write,
                "FilesProcessed": self.files_processed,
                "BytesRead": self.bytes_read,
                "EventsPersisted": self.events_persisted,
                "DatabaseFailures": self.database_failures,
                "ParserFailures": self.parser_failures,
                "Retries": self.retries,
                "CurrentOffset": self.current_offset,
                "HeartbeatCount": self.heartbeat_count,
                "ConfigReloadCount": self.config_reload_count,
                "CircuitBreakerTrips": self.cb_trips_count,
                "ParserRestarts": self.parser_restart_count,
                "WorkerRestarts": self.worker_restart_count
            }

    def get_performance_metrics(self) -> dict:
        with self.lock:
            avg_parse = sum(self.parse_times) / len(self.parse_times) if self.parse_times else 0.0
            avg_commit = sum(self.commit_times) / len(self.commit_times) if self.commit_times else 0.0
            avg_scan = sum(self.scan_times) / len(self.scan_times) if self.scan_times else 0.0
            return {
                "AverageParseTime": avg_parse,
                "AverageDbCommitTime": avg_commit,
                "AverageFileScanTime": avg_scan,
                "MaximumParseDuration": self.max_parse_duration,
                "MaximumCommitDuration": self.max_commit_duration
            }

    def reset(self):
        """Resets all metrics back to start state."""
        with self.lock:
            self._init_metrics()

metrics_tracker = MetricsTracker()
