import argparse
import sys
import os

# Ensure the script directory is in the python path to allow imports when running as a module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils import setup_logging
from cli import CLIHandler

def main() -> None:
    parser = argparse.ArgumentParser(description='Skroutz Price Alert scraper')
    parser.add_argument('--quiet', action='store_true', help='Run script with no console output')
    parser.add_argument('--status', action='store_true', help='Perform a health check of the background service and show execution status (skips main scraper)')
    parser.add_argument('--ping', action='store_true', help='Send a test notification via Apprise (skips main scraper)')
    args = parser.parse_args()

    if args.ping:
        setup_logging(args.quiet)
        CLIHandler.handle_ping()

    if args.status:
        setup_logging(False)
        CLIHandler.handle_status()

    if not args.ping and not args.status:
        setup_logging(args.quiet)
        CLIHandler.run_main_program()

if __name__ == "__main__":
    main()
