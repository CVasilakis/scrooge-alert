import os
import sys
import logging
from filelock import FileLock, Timeout

from config import LOCK_FILE_PATH, LOCK_TIMEOUT, DATA_DIR, EXIT_CODE_SKIPPED, EXIT_CODE_ERROR, EXIT_CODE_SUCCESS, EXIT_CODE_PRODUCTS_ERROR, EXIT_CODE_ENV_ERROR, EXIT_CODE_RATE_LIMIT_ERROR, PRODUCTS_FILE_PATH
from validators import ConfigValidator
from data_manager import ProductsManager
from notifier import Notifier
from utils import ErrorHandler, SystemdHelper
from clients.factory import ScraperFactory
from orchestrator import ScrapingOrchestrator

def handle_ping() -> None:
    logging.info("\nSending Skroutz Price Alert Test Notification...\n")

    ConfigValidator.print_env_status(fatal_on_error=True, show_invalid_details=True)

    notification_urls = os.environ.get("NOTIFICATION_URLS", "")
    notifier = Notifier(notification_urls)

    try:
        results = notifier.notify_test()

        if not results:
            logging.info("\n🛑 No valid notification URL(s) found.\n")
            return

        success_count = 0
        for i, (identifier, success) in enumerate(results, 1):
            if success:
                logging.info(f"    ↳ 📨 Success: URL #{i} ({identifier})")
                success_count += 1
            else:
                logging.info(f"    ↳ 🔕 Failed:  URL #{i} ({identifier})")

        total_urls = len([u for u in notification_urls.split(',') if u.strip()])
        if success_count == total_urls:
            status_icon = "✅"
        elif success_count == 0:
            status_icon = "🛑"
        else:
            status_icon = "🟡"
        logging.info(f"\n{status_icon} Test notification completed ({success_count} of {total_urls} URL(s) succeeded)!\n")
    except Exception as e:
        logging.error(f"🛑 An error occurred while sending test notification: {e}\n")

def handle_status() -> None:
    NC = '\033[0m'
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[0;33m'

    print("\nChecking Skroutz Price Alert Status...\n")

    ConfigValidator.print_update_status()
    ConfigValidator.print_prod_status(fatal_on_error=False)
    ConfigValidator.print_env_status(fatal_on_error=False)

    timer_props = SystemdHelper.get_systemd_properties('skroutz-price-alert.timer', 'ActiveState,NextElapseUSecRealtime')
    service_props = SystemdHelper.get_systemd_properties('skroutz-price-alert.service', 'ActiveState,Result,ExecMainStartTimestamp,ExecMainStatus')
    linger_enabled_val = SystemdHelper.is_linger_enabled()

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
            completed_str = f"{RED}Failed{NC} (Issue with data/products.json file)"
        elif env_error:
            completed_icon = "❗"
            completed_str = f"{RED}Failed{NC} (Issue with .env file)"
        elif rate_limit_error:
            completed_icon = "❗"
            completed_str = f"{RED}Failed{NC} (Server blocked requests due to rate limits)"
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

def run_main_program() -> None:
    logging.info("\nStarting Skroutz Price Alert...\n")

    ConfigValidator.print_update_status()
    ConfigValidator.print_prod_status(fatal_on_error=True)

    products_manager = ProductsManager(PRODUCTS_FILE_PATH)
    products_manager.load()

    ConfigValidator.print_env_status(fatal_on_error=False)

    notification_urls = os.environ.get("NOTIFICATION_URLS", "")
    notifier = Notifier(notification_urls)

    lock = FileLock(LOCK_FILE_PATH, timeout=LOCK_TIMEOUT)

    try:
        with lock:
            scraper_factory = ScraperFactory()
            try:
                orchestrator = ScrapingOrchestrator(products_manager, scraper_factory, notifier, DATA_DIR)
                orchestrator.run()
            finally:
                scraper_factory.close_all()

    except Timeout:
        logging.error('\n🛑 Skroutz Price Alert script did not start! Another instance is currently running.\n')
        sys.exit(EXIT_CODE_SKIPPED)
    except Exception:
        ErrorHandler.save_traceback(DATA_DIR)
        logging.info("")
        notifier.notify_crash()
        sys.exit(EXIT_CODE_ERROR)
