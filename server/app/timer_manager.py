# --- START server/app/timer_manager.py ---
import time
import threading
from flask import current_app # For logging if called within a request context or app context

SCENARIO_TIMERS = {}  # Stores session_id: float_unix_timestamp_of_expiry
TIMERS_LOCK = threading.Lock() # Lock for thread-safe access to SCENARIO_TIMERS

DEFAULT_DURATION_SECONDS = 30 * 60  # 30 minutes
EXTENSION_DURATION_SECONDS = 30 * 60  # 30 minutes

def init_timer(session_id, app_logger=None):
    """
    Initializes or resets a timer for the given session_id. Returns the end time (Unix timestamp).
    Uses provided app_logger or falls back to current_app.logger if in context.
    """
    # Use the provided logger, or try to get it from current_app if available
    logger = app_logger if app_logger else (current_app.logger if current_app else None)
    
    with TIMERS_LOCK:
        end_time = time.time() + DEFAULT_DURATION_SECONDS
        SCENARIO_TIMERS[session_id] = end_time
        if logger:
            logger.info(
                f"Timer initialized for session {session_id}. "
                f"Ends at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(end_time))} "
                f"(UTC: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(end_time))})."
            )
        else:
            # Fallback print if no logger is available (should not happen in normal operation with Flask)
            print(f"[TIMER_MANAGER_NO_LOGGER] Timer initialized for session {session_id}. Ends at {end_time}")
        return end_time

def extend_timer(session_id, app_logger=None):
    """
    Extends the timer for the given session_id. Returns the new end time or None.
    Uses provided app_logger or falls back to current_app.logger.
    """
    logger = app_logger if app_logger else (current_app.logger if current_app else None)
    with TIMERS_LOCK:
        if session_id in SCENARIO_TIMERS:
            # If timer somehow expired before extension, base extension on current time
            if SCENARIO_TIMERS[session_id] < time.time():
                if logger:
                    logger.warning(
                        f"Timer for session {session_id} was found expired during extension. Extending from now."
                    )
                else:
                    print(f"[TIMER_MANAGER_NO_LOGGER] Timer for session {session_id} expired, extending from now.")
                SCENARIO_TIMERS[session_id] = time.time() + EXTENSION_DURATION_SECONDS
            else:
                SCENARIO_TIMERS[session_id] += EXTENSION_DURATION_SECONDS
            
            new_end_time = SCENARIO_TIMERS[session_id]
            if logger:
                logger.info(
                    f"Timer extended for session {session_id}. "
                    f"New end time: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(new_end_time))} "
                    f"(UTC: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(new_end_time))})."
                )
            else:
                print(f"[TIMER_MANAGER_NO_LOGGER] Timer extended for session {session_id}. New end time: {new_end_time}")
            return new_end_time
        else:
            if logger:
                logger.warning(f"Attempted to extend timer for non-existent session: {session_id}")
            else:
                print(f"[TIMER_MANAGER_NO_LOGGER] Attempted to extend timer for non-existent session: {session_id}")
            return None

def remove_timer(session_id, app_logger=None):
    """
    Removes the timer for a session. Returns True if removed, False otherwise.
    Uses provided app_logger or falls back to current_app.logger.
    """
    logger = app_logger if app_logger else (current_app.logger if current_app else None)
    with TIMERS_LOCK:
        if session_id in SCENARIO_TIMERS:
            del SCENARIO_TIMERS[session_id]
            if logger:
                logger.info(f"Timer removed for session {session_id}.")
            else:
                print(f"[TIMER_MANAGER_NO_LOGGER] Timer removed for session {session_id}.")
            return True
        return False

def get_timer_end_time(session_id):
    """Gets the end time for a session's timer. Returns float Unix timestamp or None."""
    with TIMERS_LOCK:
        return SCENARIO_TIMERS.get(session_id)
# --- END server/app/timer_manager.py ---
