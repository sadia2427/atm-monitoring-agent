import datetime
import threading
from utils.logger import agent_logger

class CircuitBreakerState:
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, cooldown_seconds: float = 30.0):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.last_state_change = datetime.datetime.now()
        self.lock = threading.Lock()

        
    def can_execute(self) -> bool:
        """Checks if the breaker allows database calls. Transitions to HALF-OPEN if cooldown expired."""
        from utils.logger import log_windows_event
        from utils.metrics import metrics_tracker
        with self.lock:
            now = datetime.datetime.now()
            if self.state == CircuitBreakerState.OPEN:
                if (now - self.last_state_change).total_seconds() >= self.cooldown_seconds:
                    self.state = CircuitBreakerState.HALF_OPEN
                    self.last_state_change = now
                    agent_logger.info("Circuit Breaker transitioned to HALF-OPEN. Retrying database connection.")
                    log_windows_event("Circuit Breaker transitioned to HALF-OPEN.", level="WARNING")
                    metrics_tracker.set_circuit_breaker_state("HALF_OPEN")
                    return True
                return False
            return True

    def record_success(self):
        """Resets the breaker back to CLOSED on successful database operation."""
        from utils.logger import log_windows_event
        from utils.metrics import metrics_tracker
        with self.lock:
            if self.state != CircuitBreakerState.CLOSED:
                agent_logger.info("Circuit Breaker transitioned to CLOSED. Database connection healthy.")
                log_windows_event("Circuit Breaker transitioned to CLOSED. Database connection healthy.", level="INFO")
            self.state = CircuitBreakerState.CLOSED
            self.failure_count = 0
            self.last_state_change = datetime.datetime.now()
            metrics_tracker.set_circuit_breaker_state("CLOSED")

    def record_failure(self):
        """Increments failure count and opens the breaker if threshold exceeded."""
        from utils.logger import log_windows_event
        from utils.metrics import metrics_tracker
        with self.lock:
            self.failure_count += 1
            now = datetime.datetime.now()
            if self.failure_count >= self.failure_threshold and self.state != CircuitBreakerState.OPEN:
                self.state = CircuitBreakerState.OPEN
                self.last_state_change = now
                agent_logger.error(f"Circuit Breaker transitioned to OPEN. Database failures: {self.failure_count}. Cooldown starts.")
                log_windows_event(f"Circuit Breaker transitioned to OPEN. Database failures: {self.failure_count}.", level="ERROR")
                metrics_tracker.set_circuit_breaker_state("OPEN")


