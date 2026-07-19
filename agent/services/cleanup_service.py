import os
import time
import datetime
import zipfile
import threading
from database.models import AgentHealthLog
from settings import settings_manager
from utils.logger import agent_logger

class CleanupService:
    def __init__(self, session_factory, interval_seconds: int = 86400):
        self.session_factory = session_factory
        self.interval_seconds = interval_seconds
        self.is_running = False
        self.thread = None
        self.lock = threading.Lock()

    def start(self):
        """Starts the daily cleanup service in a daemon thread."""
        with self.lock:
            if self.is_running:
                return
            self.is_running = True
            self.thread = threading.Thread(target=self._run, name="CleanupThread", daemon=True)
            self.thread.start()
            agent_logger.info("CleanupService thread started successfully.")

    def stop(self):
        """Stops the cleanup thread."""
        with self.lock:
            if not self.is_running:
                return
            self.is_running = False
            agent_logger.info("CleanupService thread stopping...")
        if self.thread:
            try:
                self.thread.join(timeout=3.0)
            except Exception as e:
                agent_logger.error(f"Error joining cleanup thread: {e}")
            self.thread = None

    def _run(self):
        while self.is_running:
            try:
                # Sleep in short slices
                sleep_steps = self.interval_seconds * 2
                for _ in range(sleep_steps):
                    if not self.is_running:
                        break
                    time.sleep(0.5)
                
                if not self.is_running:
                    break
                    
                self.execute_cleanup()
            except Exception as e:
                agent_logger.error(f"Error in CleanupService loop: {e}")

    def execute_cleanup(self):
        """Executes the database retention cleanups and compresses/caps log directories."""
        agent_logger.info("Executing database and logs cleanup pass...")
        settings = settings_manager.get_settings()
        
        # 1. Database Retention (Purge AgentHealthLogs older than RetentionDays)
        retention_days = settings.RetentionDays if settings else 90
        cutoff = datetime.datetime.now() - datetime.timedelta(days=retention_days)
        
        session = self.session_factory()
        try:
            session.begin()
            deleted_rows = session.query(AgentHealthLog).filter(AgentHealthLog.LogTime < cutoff).delete()
            session.commit()
            if deleted_rows > 0:
                agent_logger.info(f"Database Cleanup: Purged {deleted_rows} expired AgentHealthLog rows.")
        except Exception as e:
            try:
                session.rollback()
            except Exception:
                pass
            agent_logger.error(f"Database Cleanup failed: {e}")
        finally:
            session.close()

        # 2. Log and Crash Dump Files Cap
        agent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        log_dir = agent_dir
        crash_dir = os.path.join(agent_dir, "crash")
        
        max_disk_mb = settings.MaxLogFileSizeMB if settings else 100
        max_bytes = max_disk_mb * 1024 * 1024
        
        # A. Compress crash files older than 7 days to .zip
        self._archive_old_crashes(crash_dir)
        
        # B. Enforce directory capacity limit by age
        self._enforce_disk_cap(log_dir, crash_dir, max_bytes)

    def _archive_old_crashes(self, crash_dir: str):
        if not os.path.exists(crash_dir):
            return
        try:
            now = datetime.datetime.now()
            for filename in os.listdir(crash_dir):
                if filename.endswith(".log"):
                    filepath = os.path.join(crash_dir, filename)
                    mtime = datetime.datetime.fromtimestamp(os.path.getmtime(filepath))
                    if (now - mtime).days >= 7:
                        zip_path = filepath.replace(".log", ".zip")
                        agent_logger.info(f"Archiving old crash dump '{filename}' into zip...")
                        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                            zipf.write(filepath, arcname=filename)
                        os.remove(filepath)
        except Exception as e:
            agent_logger.error(f"Archiving old crash dumps failed: {e}")

    def _enforce_disk_cap(self, log_dir: str, crash_dir: str, max_bytes: int):
        targets = []
        
        # Scan log files
        for filename in os.listdir(log_dir):
            if filename.startswith("agent.log.") or (filename.endswith(".log") and filename != "agent.log" and filename != "test_ej.log"):
                filepath = os.path.join(log_dir, filename)
                targets.append((filepath, os.path.getsize(filepath), os.path.getmtime(filepath)))
                
        # Scan crash files
        if os.path.exists(crash_dir):
            for filename in os.listdir(crash_dir):
                if filename.endswith(".log") or filename.endswith(".zip"):
                    filepath = os.path.join(crash_dir, filename)
                    targets.append((filepath, os.path.getsize(filepath), os.path.getmtime(filepath)))
                    
        # Sort targets by modification time (oldest first)
        targets.sort(key=lambda x: x[2])
        
        total_size = sum(x[1] for x in targets)
        
        active_log = os.path.join(log_dir, "agent.log")
        if os.path.exists(active_log):
            total_size += os.path.getsize(active_log)
            
        if total_size <= max_bytes:
            return
            
        agent_logger.warning(
            f"Logs folder total size ({total_size / (1024*1024):.2f}MB) exceeds "
            f"configured limit ({max_bytes / (1024*1024):.1f}MB). Purging oldest logs..."
        )
        
        for filepath, size, mtime in targets:
            try:
                os.remove(filepath)
                total_size -= size
                agent_logger.info(f"Purged old archive file: '{os.path.basename(filepath)}'")
                if total_size <= max_bytes:
                    break
            except Exception as e:
                agent_logger.error(f"Failed to purge old file '{filepath}': {e}")
