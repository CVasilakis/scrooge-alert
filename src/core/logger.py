import logging
import datetime
import traceback
import os
from typing import Optional, Dict
from logging.handlers import TimedRotatingFileHandler
from constants import LOGS_DIR

class NonEmptyFilter(logging.Filter):
    """Filter that prevents empty or whitespace-only log messages from being recorded."""
    def filter(self, record: logging.LogRecord) -> bool:
        return bool(record.getMessage().strip())

def setup_global_logging(quiet: bool = False) -> None:
    """Configures the global fallback logging level and format.

    This is used by CLI tools (ping, status) and startup messages. 
    It logs strictly to the terminal.

    Args:
        quiet (bool): If True, silences the global logger entirely.
    """
    os.makedirs(LOGS_DIR, exist_ok=True)
    
    level = logging.CRITICAL if quiet else logging.INFO
    
    # Remove all handlers associated with the root logger object to reset it
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    logging.basicConfig(level=level, format='%(message)s')

    logging.getLogger('apprise').setLevel(logging.CRITICAL)
    logging.getLogger('urllib3').setLevel(logging.CRITICAL)

def get_target_logger(target_name: str, quiet: bool = False) -> logging.Logger:
    """Creates or retrieves a configured logger for a specific scraper target.

    If 'quiet' is True, logs are written to a daily rotating file 
    ('logs/{target_name}/output.log').
    Otherwise, logs are output to the terminal via the root logger.

    Args:
        target_name (str): The identifier for the scraper (e.g., 'skroutz').
        quiet (bool): If True, logs to file silently. Otherwise, logs to terminal.

    Returns:
        logging.Logger: The configured logger instance.
    """
    logger = logging.getLogger(f"scraper.{target_name}")
    logger.setLevel(logging.INFO)
    
    # Prevent the logger from passing messages to the root logger when in quiet mode
    # so we don't accidentally print to terminal
    logger.propagate = not quiet

    # If handlers already exist, return the logger to prevent duplicate logs
    if logger.handlers:
        return logger

    if quiet:
        log_format = '[%(asctime)s] %(message)s'
        date_format = '%Y-%m-%d %H:%M:%S'

        target_logs_dir = os.path.join(LOGS_DIR, target_name)
        os.makedirs(target_logs_dir, exist_ok=True)
        log_path = os.path.join(target_logs_dir, "output.log")

        rotating_handler = TimedRotatingFileHandler(
            log_path, when="midnight", interval=1, backupCount=7, encoding='utf-8'
        )
        rotating_handler.addFilter(NonEmptyFilter())
        rotating_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))
        
        logger.addHandler(rotating_handler)

    return logger

def save_traceback(logger: logging.Logger, target_name: Optional[str] = None, url: Optional[str] = None, headers: Optional[Dict[str, str]] = None) -> None:
    """Saves the current exception traceback to a target-specific error log file.

    Args:
        logger (logging.Logger): The logger instance to log the error summary to.
        target_name (Optional[str]): The identifier for the scraper. If None, saves to root logs dir.
        url (Optional[str]): The URL associated with the error, if any.
        headers (Optional[Dict[str, str]]): HTTP headers associated with the error, if any.
    """
    if target_name:
        target_logs_dir = os.path.join(LOGS_DIR, target_name)
    else:
        target_logs_dir = LOGS_DIR
        
    os.makedirs(target_logs_dir, exist_ok=True)
    
    log_path = os.path.join(target_logs_dir, "errors.txt")
    logger.error(f"🛑 An error occurred! Check {log_path} for details.")
    
    time_now = datetime.datetime.now().strftime("%Y-%m-%d (%H:%M:%S)")
    with open(log_path, "a", newline='') as log_file:
        log_file.write(f"\n\nAn error occurred at {time_now}:\n")
        if url:
            log_file.write(f"URL: {url}\n")
        if headers:
            header_id = f"Platform: {headers.get('sec-ch-ua-platform', 'Unknown')}, Lang: {headers.get('accept-language', 'Unknown')}"
            log_file.write(f"Header ID: {header_id}\n")
        traceback.print_exc(file=log_file)
        log_file.write(f"\n{'-'*100}")
