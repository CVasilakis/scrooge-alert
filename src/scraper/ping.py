import os
import sys
import logging

# Ensure the script directory is in the python path to allow imports when running as a module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from validators import ConfigValidator
from notifier import Notifier
from logger import setup_logging

def main():
    """Main entry point for sending a test notification.

    This function initializes the notifier with URLs from the environment and sends
    a test message, reporting the success or failure of each configured service.
    """
    setup_logging()

    logging.info("")
    logging.info("Sending Skroutz Price Alert Test Notification...")
    logging.info("")

    ConfigValidator.print_env_status(fatal_on_error=True, show_invalid_details=True)

    notification_urls = os.environ.get("NOTIFICATION_URLS", "")
    notifier = Notifier(notification_urls)

    try:
        results = notifier.notify_test()

        if not results:
            logging.info("")
            logging.info("🛑 No valid notification URL(s) found.")
            logging.info("")
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
        logging.info("")
        logging.info(f"{status_icon} Test notification completed ({success_count} of {total_urls} URL(s) succeeded)!")
        logging.info("")
    except Exception as e:
        logging.error(f"🛑 An error occurred while sending test notification: {e}")
        logging.info("")

if __name__ == "__main__":
    main()
