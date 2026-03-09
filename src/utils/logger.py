import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from config.settings import settings

def setup_logger(name: str = "NeuroSync", level=logging.INFO):
    """
    Sets up a logger with both file and console handlers.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Prevent adding handlers multiple times
    if logger.hasHandlers():
        return logger

    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 1. File Handler (Rotating)
    log_file = os.path.join(settings.LOG_DIR, "app.log")
    file_handler = RotatingFileHandler(
        log_file, maxBytes=5*1024*1024, backupCount=3  # 5MB per file, keep 3
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # 2. Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger

# Create a default logger instance
logger = setup_logger()
