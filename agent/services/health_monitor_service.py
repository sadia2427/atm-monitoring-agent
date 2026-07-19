import os
import time
import threading
from utils.logger import agent_logger, log_windows_event
from utils.metrics import metrics_tracker

class HealthMonitorService:
    def __init__(self, monitor_service, heartbeat_service, max_restarts: int = 5, check_interval: int = 10):
        self.monitor_service = monitor_service
        self.heartbeat_service = heartbeat_service
        self.max_restarts = max_restarts
        self.check_interval = check_interval
        
        self.is_running = False
        self.thread = None
        self.lock = threading.Lock()
        
        self.monitor_restarts = 0
        self.heartbeat_restarts = 0

    def start(self):
        """Starts the central worker watchdog monitoring thread."""
        with self.lock:
            if self.is_running:
                return
            self.is_running = True
            self.thread = threading.Thread(target=self._run, name="HealthMonitorThread", daemon=True)
            self.thread.start()
            agent_logger.info("HealthMonitorService started successfully.")

    def stop(self):
        """Stops the health monitor thread cleanly."""
        with self.lock:
            if not self.is_running:
                return
            self.is_running = False
            agent_logger.info("HealthMonitorService stopping...")
        if self.thread:
            try:
                self.thread.join(timeout=3.0)
            except Exception as e:
                agent_logger.error(f"Error joining health monitor thread: {e}")
            self.thread = None

    def _run(self):
        while self.is_running:
            try:
                # Sleep in short slices
                sleep_steps = self.check_interval * 2
                for _ in range(sleep_steps):
                    if not self.is_running:
                        break
                    time.sleep(0.5)
                
                if not self.is_running:
                    break
                    
                self._check_services()
            except Exception as e:
                agent_logger.error(f"Error in HealthMonitorService loop: {e}")

    def _check_services(self):
        # 1. Check Log Polling Thread
        mon = self.monitor_service
        if mon and mon.is_running:
            # Check polling thread
            if mon.polling_thread and not mon.polling_thread.is_alive():
                agent_logger.error("Health Monitor detected: Log Polling Thread has CRASHED or STOPPED.")
                log_windows_event("Log Polling Thread has CRASHED or STOPPED.", level="ERROR")
                if self.monitor_restarts < self.max_restarts:
                    self.monitor_restarts += 1
                    agent_logger.warning(f"Self Recovery: Restarting Polling Thread (Attempt {self.monitor_restarts}/{self.max_restarts})...")
                    metrics_tracker.record_worker_restart()
                    
                    mon.polling_thread = threading.Thread(target=mon._polling_loop, name="LogPollingThread", daemon=True)
                    mon.polling_thread.start()
                    agent_logger.info("Polling Thread restarted successfully.")
                else:
                    agent_logger.critical("Self Recovery LIMIT EXCEEDED: Polling Thread cannot be restarted further.")
                    log_windows_event("Polling Thread restart limit exceeded.", level="ERROR")

            # Check Watchdog Observer
            if mon.observer and not mon.observer.is_alive():
                agent_logger.error("Health Monitor detected: Watchdog Observer Thread has CRASHED or STOPPED.")
                log_windows_event("Watchdog Observer Thread has CRASHED or STOPPED.", level="ERROR")
                if self.monitor_restarts < self.max_restarts:
                    self.monitor_restarts += 1
                    agent_logger.warning(f"Self Recovery: Re-initializing Watchdog Observer (Attempt {self.monitor_restarts}/{self.max_restarts})...")
                    metrics_tracker.record_worker_restart()
                    try:
                        mon.observer.stop()
                    except Exception:
                        pass
                    
                    from watchdog.observers import Observer
                    from services.file_monitor_service import LogFileEventHandler
                    mon.observer = Observer()
                    event_handler = LogFileEventHandler(mon.file_path, mon.trigger_scan)
                    target_dir = os.path.dirname(mon.file_path)
                    mon.observer.schedule(event_handler, path=target_dir if target_dir else ".", recursive=False)
                    mon.observer.start()
                    agent_logger.info("Watchdog Observer restarted successfully.")
                else:
                    agent_logger.critical("Self Recovery LIMIT EXCEEDED: Watchdog Observer cannot be restarted further.")

        # 2. Check Heartbeat Thread
        hb = self.heartbeat_service
        if hb and hb.is_running:
            if hb.thread and not hb.thread.is_alive():
                agent_logger.error("Health Monitor detected: Heartbeat Thread has CRASHED or STOPPED.")
                log_windows_event("Heartbeat Thread has CRASHED or STOPPED.", level="ERROR")
                if self.heartbeat_restarts < self.max_restarts:
                    self.heartbeat_restarts += 1
                    agent_logger.warning(f"Self Recovery: Restarting Heartbeat Thread (Attempt {self.heartbeat_restarts}/{self.max_restarts})...")
                    metrics_tracker.record_worker_restart()
                    
                    hb.thread = threading.Thread(target=hb._run, name="HeartbeatThread", daemon=True)
                    hb.thread.start()
                    agent_logger.info("Heartbeat Thread restarted successfully.")
                else:
                    agent_logger.critical("Self Recovery LIMIT EXCEEDED: Heartbeat Thread cannot be restarted further.")
                    log_windows_event("Heartbeat Thread restart limit exceeded.", level="ERROR")
