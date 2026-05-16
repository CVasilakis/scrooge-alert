import argparse
import sys
import os

# Ensure the script directory is in the python path to allow imports when running as a module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils import setup_logging
from cli import handle_ping, handle_status, run_main_program

def main() -> None:
    parser = argparse.ArgumentParser(description='Skroutz Price Alert scraper')
    parser.add_argument('--quiet', action='store_true', help='Run script with no console output')
    parser.add_argument('--status', action='store_true', help='Perform a health check of the background service and show execution status (skips main scraper)')
    parser.add_argument('--ping', action='store_true', help='Send a test notification via Apprise (skips main scraper)')
    args = parser.parse_args()

    if args.ping:
        setup_logging(args.quiet)
        handle_ping()

    if args.status:
        setup_logging(False)
        handle_status()

    if not args.ping and not args.status:
        setup_logging(args.quiet)
        run_main_program()

if __name__ == "__main__":
    main()
