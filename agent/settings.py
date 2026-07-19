import datetime
import threading
from sqlalchemy.orm import Session
from database.models import AgentSettings
from database.db import SessionLocal

class AgentSettingsCache:
    _instance = None
    _static_lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        with cls._static_lock:
            if not cls._instance:
                cls._instance = super(AgentSettingsCache, cls).__new__(cls, *args, **kwargs)
                cls._instance._init_cache()
            return cls._instance

    def _init_cache(self):
        self.lock = threading.Lock()
        self._cached_settings = None
        self._last_loaded = None

    def load_settings(self, force: bool = False) -> AgentSettings:
        """
        Loads the active settings record from the database and caches it.
        If the database is empty, returns a default settings object in memory.
        """
        with self.lock:
            now = datetime.datetime.now()
            # Serve from cache if loaded less than 300 seconds (5 minutes) ago and not forced
            if (
                not force 
                and self._cached_settings 
                and self._last_loaded 
                and (now - self._last_loaded).total_seconds() < 300
            ):
                return self._cached_settings
                
            session = SessionLocal()
            try:
                # Query the first configuration row
                settings = session.query(AgentSettings).order_by(AgentSettings.Id.asc()).first()
                if not settings:
                    # Fallback defaults in case seed settings are missing
                    settings = AgentSettings(
                        Id=0,
                        PollingIntervalSeconds=5,
                        HeartbeatIntervalSeconds=30,
                        PingIntervalSeconds=300,
                        LogScanIntervalSeconds=2,
                        OfflineThresholdMinutes=60,
                        CriticalOfflineThresholdMinutes=120,
                        LowCashThresholdAmount=500000,
                        EJLogPath="C:\\EJ\\ncr_ej.log",
                        RetentionDays=90,
                        MaxLogFileSizeMB=100,
                        EnableHeartbeat=True,
                        EnablePing=True,
                        EnableLogParser=True,
                        EnableAutoRecovery=False,
                        AgentVersion="1.0.0"
                    )
                
                # Validation check
                errors = []
                poll_val = getattr(settings, "PollingIntervalSeconds", None)
                scan_val = getattr(settings, "LogScanIntervalSeconds", None)
                offline_val = getattr(settings, "OfflineThresholdMinutes", None)
                hb_val = getattr(settings, "HeartbeatIntervalSeconds", None)
                cash_val = getattr(settings, "LowCashThresholdAmount", None)
                
                if poll_val is not None and poll_val <= 0:
                    errors.append(f"PollingIntervalSeconds must be > 0 (got {poll_val})")
                if scan_val is not None and scan_val <= 0:
                    errors.append(f"LogScanIntervalSeconds must be > 0 (got {scan_val})")
                if offline_val is not None and offline_val <= 0:
                    errors.append(f"OfflineThresholdMinutes must be > 0 (got {offline_val})")
                if hb_val is not None and hb_val <= 0:
                    errors.append(f"HeartbeatIntervalSeconds must be > 0 (got {hb_val})")
                if cash_val is not None and cash_val < 0:
                    errors.append(f"LowCashThresholdAmount must be >= 0 (got {cash_val})")
                    
                if errors:
                    from utils.logger import agent_logger
                    agent_logger.error(f"Configuration validation failed: {', '.join(errors)}")
                    if self._cached_settings:
                        agent_logger.info("Keeping the previous valid configuration.")
                        return self._cached_settings
                else:
                    session.expunge(settings)
                    self._cached_settings = settings
                    try:
                        from utils.metrics import metrics_tracker
                        metrics_tracker.record_config_reload()
                    except Exception:
                        pass
                
                self._last_loaded = now
                return self._cached_settings
            finally:
                session.close()

    def get_settings(self) -> AgentSettings:
        """Returns the currently cached settings or loads them from database."""
        # load_settings handles its own synchronization lock
        return self.load_settings()

# Global settings manager singleton
settings_manager = AgentSettingsCache()
