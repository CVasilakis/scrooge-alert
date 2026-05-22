import logging
import datetime
import traceback
import os
import subprocess
from typing import Optional, Dict

def setup_logging(quiet: bool = False) -> None:
    """Configures the application's logging level and format.
    
    Args:
        quiet (bool): If True, sets logging level to WARNING. Otherwise, INFO.
    """
    level = logging.WARNING if quiet else logging.INFO
    logging.basicConfig(level=level, format='%(message)s')
    logging.getLogger('apprise').setLevel(logging.CRITICAL)
    logging.getLogger('urllib3').setLevel(logging.CRITICAL)

def save_traceback(data_dir: str, url: Optional[str] = None, headers: Optional[Dict[str, str]] = None) -> None:
    """Saves the current exception traceback to an error log file.
    
    Args:
        data_dir (str): The directory where the error log file will be saved.
        url (Optional[str]): The URL associated with the error, if any.
        headers (Optional[Dict[str, str]]): HTTP headers associated with the error, if any.
    """
    logging.error("🛑 An error occurred. Check data/error_log.txt for details.")
    log_path = os.path.join(data_dir, "error_log.txt")
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

def get_systemd_properties(unit: str, properties: str) -> dict:
    """Retrieves specified properties for a given systemd user unit.
    
    Args:
        unit (str): The name of the systemd unit (e.g., 'service.timer').
        properties (str): A comma-separated list of properties to query.
        
    Returns:
        dict: A dictionary mapping property names to their values.
    """
    service_file_path = os.path.expanduser(f'~/.config/systemd/user/{unit}')
    if not os.path.exists(service_file_path) or os.path.getsize(service_file_path) == 0:
        return {}

    try:
        output = subprocess.check_output(
            ['systemctl', '--user', 'show', unit, f'--property={properties}'],
            stderr=subprocess.DEVNULL
        ).decode('utf-8').strip()
        if not output:
            return {}
        return dict(line.split('=', 1) for line in output.splitlines() if '=' in line)
    except (subprocess.CalledProcessError, ValueError):
        return {}

def is_linger_enabled() -> bool:
    """Checks if systemd user lingering is enabled for the current user.
    
    Returns:
        bool: True if linger is enabled, False otherwise.
    """
    try:
        user_id = os.environ.get("USER") or os.environ.get("LOGNAME") or "nobody"
        output = subprocess.check_output(
            ['loginctl', 'show-user', user_id, '--property=Linger'],
            stderr=subprocess.DEVNULL
        ).decode('utf-8').strip()
        return "Linger=yes" in output
    except subprocess.CalledProcessError:
        return False
