import sys
import os
import logging

# Ensure the script directory is in the python path to allow imports when running as a module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from constants import EXIT_CODE_SKIPPED, EXIT_CODE_SUCCESS, EXIT_CODE_PRODUCTS_ERROR, EXIT_CODE_ENV_ERROR, EXIT_CODE_RATE_LIMIT_ERROR, EXIT_CODE_INTERRUPT
from validators import ConfigValidator
from updater import InteractiveUpdateChecker
from utils import get_systemd_properties, is_linger_enabled
from logger import setup_logging

def main():
    """Main entry point for checking the status of the Skroutz Price Alert service.

    This function retrieves status information from systemd, validates configuration,
    checks for updates, and prints a formatted status report to the console.
    """
    NC = '\033[0m'
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[0;33m'

    setup_logging()

    logging.info("")
    logging.info("Checking Skroutz Price Alert Status...")
    logging.info("")

    update_checker = InteractiveUpdateChecker()
    update_checker.check()
    ConfigValidator.print_prod_status(fatal_on_error=False)
    ConfigValidator.print_env_status(fatal_on_error=False)

    timer_props = get_systemd_properties('skroutz-price-alert.timer', 'ActiveState,NextElapseUSecRealtime')
    service_props = get_systemd_properties('skroutz-price-alert.service', 'ActiveState,Result,ExecMainStartTimestamp,ExecMainStatus')
    linger_enabled_val = is_linger_enabled()

    linger_icon = "✅" if linger_enabled_val else "❗"
    linger_enabled = f"{GREEN}Yes{NC}" if linger_enabled_val else f"{RED}No{NC}"

    timer_active_val = timer_props.get("ActiveState") == "active"
    timer_icon = "✅" if timer_active_val else "❗"
    timer_active = f"{GREEN}Yes{NC}" if timer_active_val else f"{RED}No{NC}"

    result = service_props.get("Result", "")
    exec_status = service_props.get("ExecMainStatus", "")
    last_exec_time = service_props.get("ExecMainStartTimestamp", "")
    service_active = service_props.get("ActiveState", "")

    no_errors = (result == "success" and exec_status == str(EXIT_CODE_SUCCESS))
    skipped = (exec_status == str(EXIT_CODE_SKIPPED))
    products_error = (exec_status == str(EXIT_CODE_PRODUCTS_ERROR))
    env_error = (exec_status == str(EXIT_CODE_ENV_ERROR))
    rate_limit_error = (exec_status == str(EXIT_CODE_RATE_LIMIT_ERROR))
    interrupted = (exec_status == str(EXIT_CODE_INTERRUPT))
    is_currently_running = service_active in ("active", "activating")
    is_pending_first_execution = timer_active_val and not last_exec_time

    next_exec = timer_props.get("NextElapseUSecRealtime", "")
    if is_currently_running:
        next_exec = f"{GREEN}Running Now{NC}"
        next_exec_icon = "✅"
    elif not next_exec or next_exec in ("n/a", "0"):
        next_exec = f"{RED}Not Scheduled{NC}"
        next_exec_icon = "❗"
    else:
        next_exec_icon = "✅"

    if not last_exec_time:
        last_exec_time = f"{RED}Never{NC}"
        completed_str = f"{RED}Not executed yet{NC}"
        last_exec_icon = "❗"
        completed_icon = "❗"
    else:
        last_exec_icon = "✅"
        error_details = "None" if no_errors else f"Reason: {result or 'Unknown'}, Exit Code: {exec_status or 'Unknown'}"
        if no_errors:
            completed_icon = "✅"
            completed_str = f"{GREEN}OK{NC}"
        elif skipped:
            completed_icon = "🟡"
            completed_str = f"{YELLOW}Skipped{NC} (Another instance was running)"
        elif products_error:
            completed_icon = "❗"
            completed_str = f"{RED}Failed{NC} (Issue with config/skroutz.json file)"
        elif env_error:
            completed_icon = "❗"
            completed_str = f"{RED}Failed{NC} (Issue with .env file)"
        elif rate_limit_error:
            completed_icon = "❗"
            completed_str = f"{RED}Failed{NC} (Server blocked requests due to rate limits)"
        elif interrupted:
            completed_icon = "🟡"
            completed_str = f"{YELLOW}Interrupted{NC} (User or system interrupt)"
        else:
            completed_icon = "❗"
            completed_str = f"{RED}Failed{NC} ({error_details})"

    print(f"\n{linger_icon} Linger Enabled:              {linger_enabled}")
    print(f"{timer_icon} Systemd Timer Active:        {timer_active}")
    if last_exec_time != f"{RED}Never{NC}":
        print(f"{last_exec_icon} Last Execution Time:         {last_exec_time}")
        print(f"{completed_icon} Last Execution Status:       {completed_str}")
    print(f"{next_exec_icon} Next Scheduled Execution:    {next_exec}")

    if is_currently_running:
        print("    ↳ Script is currently running in the background. Check again in a few minutes.")
    elif is_pending_first_execution:
        print("    ↳ Timer pending first execution. Waiting for the scheduled time.")
    print("")

if __name__ == "__main__":
    main()
