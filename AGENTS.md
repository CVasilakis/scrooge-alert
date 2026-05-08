# Skroutz Price Alert - Development Context

## Project Overview
This project is an automated Python application designed to monitor product prices across Skroutz domains and send push notifications when prices drop below user-defined target thresholds. 

- **Main Technologies:** Python 3, `apprise` (for versatile push notifications via Telegram, Discord, etc.), `tls_client` (for evasive web scraping by mimicking browser TLS fingerprints), and systemd (for automated background scheduling on Linux).
- **Architecture:** The core application logic resides in `src/scraper/skroutz_price_alert.py`. User configuration is completely externalized to `.env` (notification endpoints) and `data/products.json` (the list of tracked products). It is designed to run silently as a background task, leveraging a local Python virtual environment (`venv`) to isolate dependencies.

## Building and Running
The application is primarily intended for automated background execution but provides wrapper scripts for easy management and manual testing.

- **Installation:** Execute `./install.sh`. This script creates the Python virtual environment, installs dependencies, and configures an hourly systemd user timer.
- **Automated Execution:** Handled automatically by the systemd service (`skroutz-price-alert.timer`).
- **Manual Execution:** Execute `./scripts/run_scraper.sh` to run the scraper interactively and view output logs in the terminal.
- **Testing Notifications:** Run `./scripts/run_scraper.sh --ping` to send a test payload and verify that the Apprise URLs in your `.env` file are configured correctly.
- **Health Checks:** Run `./scripts/run_scraper.sh --status` to perform a comprehensive health check. This validates the configuration (products and notification settings), checks for available script updates, and verifies the status of the background systemd service and timer.
- **Uninstallation:** Execute `./uninstall.sh` to cleanly stop and disable the systemd services and remove the virtual environment (user data is preserved).

## Development Conventions
- **Scraping Practices & Rate Limiting:** The scraper intentionally paces requests using a base delay (20s) plus randomized jitter (1-5s) between product checks to avoid triggering Skroutz's anti-bot protections. Concurrency is avoided to maintain a low profile.
- **Data Integrity:** Updates to the `data/products.json` file (such as logging the latest price and check timestamp) are performed using an atomic save mechanism to prevent file corruption in case of unexpected interruptions.
- **Error Handling & Logging:** When running silently in the background, exceptions are caught and logged to `data/error_log.txt`. If critical errors occur (like repeated scraping failures or a total crash), the script utilizes the Apprise notifier to alert the user of the failure.
- **Code Style:** Standard Python procedural and object-oriented practices (e.g., `ProductsManager`, `SkroutzScraper`, `Notifier`) are used to compartmentalize logic. Configuration and state are decoupled from the main execution logic.
