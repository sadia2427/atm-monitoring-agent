import os
import time
import hashlib
from typing import Tuple, List

def calculate_file_hash(file_path: str) -> str:
    """
    Calculates the SHA-256 hash of a file.
    Retries automatically with exponential backoff if the file is temporarily locked.
    """
    if not os.path.exists(file_path):
        return ""
        
    delays = [0.05, 0.1, 0.2, 0.4, 0.8]
    for attempt, delay in enumerate(delays):
        try:
            hasher = hashlib.sha256()
            with open(file_path, "rb") as f:
                block = f.read(65536)
                while len(block) > 0:
                    hasher.update(block)
                    block = f.read(65536)
            return hasher.hexdigest()
        except (PermissionError, OSError) as e:
            if attempt == len(delays) - 1:
                return ""
            time.sleep(delay)
    return ""

def read_appended_lines(file_path: str, offset: int, max_bytes: int = 10 * 1024 * 1024) -> Tuple[List[str], int, int]:
    """
    Reads new appended lines from a file starting from the given offset, up to max_bytes.
    Handles temporary file locks with automatic exponential backoff retries.
    Avoids loading the entire file into memory (Memory Protection).
    Returns (lines, new_offset, current_file_size).
    """
    if not os.path.exists(file_path):
        return [], offset, 0
        
    delays = [0.05, 0.1, 0.2, 0.4, 0.8]
    for attempt, delay in enumerate(delays):
        try:
            file_size = os.path.getsize(file_path)
            # Reset offset if file has been truncated/rotated
            if file_size < offset:
                offset = 0
                
            lines = []
            bytes_read = 0
            
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(offset)
                while bytes_read < max_bytes:
                    line = f.readline()
                    if not line:
                        break
                    lines.append(line)
                    bytes_read += len(line.encode("utf-8", errors="ignore"))
                new_offset = f.tell()
                
            return lines, new_offset, file_size
        except (PermissionError, OSError) as e:
            if attempt == len(delays) - 1:
                # Final attempt failed
                return [], offset, 0
            time.sleep(delay)
    return [], offset, 0
