import os
import subprocess

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
