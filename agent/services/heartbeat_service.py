import time
import datetime
import threading
from utils.logger import agent_logger
from utils.metrics import metrics_tracker
from version import get_version_info
from config import config
from database.models import ATM, ATMLiveStatus
from settings import settings_manager

class HeartbeatService:
    def __init__(self, atm_id: int, session_factory, interval: int = 30):
        self.atm_id = atm_id
        self.session_factory = session_factory
        self.interval = interval
        self.is_running = False
        self.thread = None
        self.lock = threading.Lock()
        self.monitor_service = None
        self.health_monitor_service = None

    def set_services(self, monitor_service, health_monitor_service):
        self.monitor_service = monitor_service
        self.health_monitor_service = health_monitor_service

    def start(self):
        """Starts the independent heartbeat execution loop in a daemon thread."""
        with self.lock:
            if self.is_running:
                return
            self.is_running = True
            self.thread = threading.Thread(target=self._run, name="HeartbeatThread", daemon=True)
            self.thread.start()
            agent_logger.info("HeartbeatService thread started successfully.")

    def stop(self):
        """Stops the heartbeat loop cleanly."""
        with self.lock:
            if not self.is_running:
                return
            self.is_running = False
            agent_logger.info("HeartbeatService thread stopping...")
        if self.thread:
            try:
                self.thread.join(timeout=3.0)
            except Exception as e:
                agent_logger.error(f"Error joining heartbeat thread: {e}")
            self.thread = None

    def _run(self):
        while self.is_running:
            try:
                # Load configuration dynamically to adapt changes instantly
                settings = settings_manager.get_settings()
                current_interval = settings.HeartbeatIntervalSeconds if settings else self.interval
                
                # Sleep in 500ms intervals to support near-instantaneous shutdown
                sleep_steps = int(max(1, current_interval) * 2)
                for _ in range(sleep_steps):
                    if not self.is_running:
                        break
                    time.sleep(0.5)
                
                if not self.is_running:
                    break
                    
                self._send_heartbeat()
            except Exception as e:
                agent_logger.error(f"Error in HeartbeatService loop: {e}")
                time.sleep(self.interval)

    def _send_heartbeat(self):
        """Performs database-driven heartbeat persistence."""
        session = self.session_factory()
        try:
            session.begin()
            
            atm = session.query(ATM).filter(ATM.Id == self.atm_id).first()
            version_info = get_version_info(terminal_id=config.atm_terminal_id)
            
            if atm:
                atm.LastHeartbeat = datetime.datetime.now()
                atm.AgentVersion = version_info["AgentVersion"]
                atm.HostName = version_info["Hostname"]
                atm.AgentName = config.agent_name
                atm.UpdatedOn = datetime.datetime.now()
            
            status = session.query(ATMLiveStatus).filter(ATMLiveStatus.ATMId == self.atm_id).first()
            if status:
                status.LastAgentHeartbeat = datetime.datetime.now()
                status.UpdatedOn = datetime.datetime.now()
            
            session.commit()
            metrics_tracker.record_heartbeat()
            
            try:
                from utils.diagnostics import generate_diagnostics_snapshot
                parser_service = self.monitor_service.parser_service if self.monitor_service else None
                generate_diagnostics_snapshot(
                    self.atm_id,
                    self.monitor_service.file_path if self.monitor_service else "",
                    parser_service,
                    self.monitor_service,
                    self,
                    self.health_monitor_service
                )
            except Exception as diag_err:
                agent_logger.error(f"Failed to generate diagnostics snapshot: {diag_err}")
            
        except Exception as e:
            try:
                session.rollback()
            except Exception:
                pass
            agent_logger.error(f"Failed to persist agent heartbeat: {e}")
        finally:
            session.close()
