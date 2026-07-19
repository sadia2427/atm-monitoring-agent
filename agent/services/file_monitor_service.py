import os
import time
import threading
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from utils.logger import agent_logger
from services.parser_service import ParserService
from settings import settings_manager

class LogFileEventHandler(FileSystemEventHandler):
    def __init__(self, target_path: str, callback):
        super().__init__()
        self.target_path = os.path.abspath(target_path)
        self.callback = callback

    def on_modified(self, event):
        if not event.is_directory and os.path.abspath(event.src_path) == self.target_path:
            self.callback()

class FileMonitorService:
    def __init__(self, atm_id: int, file_path: str, parser_service: ParserService, scan_interval: int = 5):
        self.atm_id = atm_id
        self.file_path = os.path.abspath(file_path)
        self.parser_service = parser_service
        self.scan_interval = scan_interval
        
        self.is_running = False
        self.observer = None
        self.lock = threading.Lock()
        self.polling_thread = None

    def start(self):
        """Starts both Watchdog file system observer and fallback polling loop."""
        if self.is_running:
            return
            
        self.is_running = True
        agent_logger.info("=== File Monitoring Service Starting ===")
        agent_logger.info(f"Target EJ Log: '{self.file_path}'")
        agent_logger.info(f"Fallback Scan Interval: {self.scan_interval}s")

        # Initial parse scan on startup
        self.trigger_scan()

        # 1. Start Watchdog Observer
        target_dir = os.path.dirname(self.file_path)
        if target_dir:
            os.makedirs(target_dir, exist_ok=True)
            
        try:
            self.observer = Observer()
            event_handler = LogFileEventHandler(self.file_path, self.trigger_scan)
            self.observer.schedule(event_handler, path=target_dir if target_dir else ".", recursive=False)
            self.observer.start()
            agent_logger.info("Watchdog file observer started successfully.")
        except Exception as e:
            agent_logger.error(f"Failed to start Watchdog file observer: {e}. Falling back to polling only.")
            self.observer = None

        # 2. Start fallback polling thread
        self.polling_thread = threading.Thread(target=self._polling_loop, name="LogPollingThread", daemon=True)
        self.polling_thread.start()
        agent_logger.info("Fallback polling thread started successfully.")
        agent_logger.info("Monitoring Started.")

    def stop(self):
        """Stops the monitoring loops and waits for active scans to finish."""
        if not self.is_running:
            return
            
        agent_logger.info("=== File Monitoring Service Stopping ===")
        self.is_running = False
        
        # Thread safety check: acquiring self.lock blocks until any active trigger_scan finishes
        with self.lock:
            agent_logger.info("No active scans in progress. Clean checkpoint verified.")
        
        if self.observer:
            try:
                self.observer.stop()
                self.observer.join()
            except Exception as e:
                agent_logger.error(f"Error stopping Watchdog observer: {e}")
            self.observer = None
            
        # Flush logging system
        logging.shutdown()
        agent_logger.info("File monitoring stopped gracefully.")

    def trigger_scan(self):
        """Thread-safe scan invocation."""
        with self.lock:
            if not self.is_running:
                return
            try:
                # Reload configuration dynamically
                settings = settings_manager.get_settings()
                if settings and not settings.EnableLogParser:
                    agent_logger.info("Log parsing is disabled in settings. Skipping scan.")
                    return
                    
                self.parser_service.process_file(self.atm_id, self.file_path)
            except Exception as e:
                agent_logger.error(f"Error during file scan: {e}")

    def _polling_loop(self):
        """Continuous polling fallback loop with dynamic config reload and slice sleep."""
        while self.is_running:
            try:
                # Load settings dynamically to reflect modifications immediately (hot reload)
                settings = settings_manager.get_settings()
                interval = settings.LogScanIntervalSeconds if settings else self.scan_interval
                
                # Sleep in 100ms chunks to enable near-instantaneous shutdown response
                sleep_steps = int(max(0.1, interval) * 10)
                for _ in range(sleep_steps):
                    if not self.is_running:
                        break
                    time.sleep(0.1)
                    
                if self.is_running:
                    self.trigger_scan()
            except Exception as e:
                agent_logger.error(f"Error in polling loop: {e}")
                time.sleep(self.scan_interval)
