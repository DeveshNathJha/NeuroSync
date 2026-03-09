# file: src/utils/logger.py

## 1. File Overview
**Purpose**: **System Logging Infrastructure**.
**Role**: Provides a standard way to log debug/info/error messages to both the Console and a File.
**Why**: `print()` statements are bad practice in production and cannot be rotated or filtered.

## 2. Code Breakdown

### `setup_logger` (Lines 7-36)
-   **Singleton-ish**: Checks `if logger.hasHandlers()` to prevent duplicate logs (which causes the "message repeated 10 times" bug).
-   **Rotation**: Uses `RotatingFileHandler`.
    -   `maxBytes=5MB`: Keeps log files small.
    -   `backupCount=3`: Keeps only the last 3 files (`app.log`, `app.log.1`, `app.log.2`).

## 3. How to Use
```python
from src.utils.logger import logger
logger.info("System started")
logger.error("Database connection failed")
```

## 4. Design Decisions
-   **Format**: `%(asctime)s - %(name)s - %(levelname)s - %(message)s`. Standard timestamped format.

## 5. Limitations
-   **Blocking**: Standard Python logging is blocking. If the disk is slow, the app slows down.
