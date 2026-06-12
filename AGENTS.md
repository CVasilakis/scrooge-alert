# Scrooge Alert - Development Context

## Project Overview
This project is an automated Python application designed to monitor product prices across Skroutz domains and send push notifications when prices drop below user-defined target thresholds. 

- **Main Technologies:** Python 3, `apprise` (for versatile push notifications via Telegram, Discord, etc.), `tls_client` (for evasive web scraping by mimicking browser TLS fingerprints), and systemd (for automated background scheduling on Linux).
- **Architecture:** The application features a modular, plugin-based architecture residing in `src/core/`. The entrypoint is `main.py`, which delegates to specialized modules:
  - **Scrapers (`scrapers/`)**: Self-contained plugin packages grouped by target store. Each plugin (e.g. `scrapers/skroutz/`) contains its own client, model, storage, and a `plugin.py` descriptor that acts as the single source of truth for domains, config filenames, and class bindings.
    - **Base Contracts (`scrapers/base/`)**: Abstract base classes (`BaseScraperClient`, `BaseTrackedItem`, `ScrapeResult`, `BaseDataManager`, `BasePlugin`) defining the interfaces all plugins must implement.
    - **Registry (`scrapers/registry.py`)**: A unified `ScraperRegistry` that replaces the old separate `ScraperFactory` and `DataManagerFactory`. Handles URL-to-plugin resolution, lazy client/manager instantiation, and auto-discovery of plugins via `pkgutil`.
  - **Orchestration (`orchestrator.py`)**: `ScrapingOrchestrator` runs a store-agnostic execution loop.
  - **Configuration & Validation (`constants.py`, `utils.py`)**: Centralized constants and environment/file health checks.
  - **Terminal UI (`tui.py`)**: Manages the interactive progress bar during sleep intervals using the Strategy pattern (`ExecutionStrategy`).
  - **CLI Tools (`ping.py`, `status.py`)**: Dedicated scripts for specific CLI commands to maintain separation of concerns.
  User configuration is completely externalized to `.env` (notification endpoints) and `config/skroutz.json` (the list of tracked products). It is designed to run silently as a background task, leveraging a local Python virtual environment (`venv`) to isolate dependencies.

## Building and Running
The application is primarily intended for automated background execution but provides wrapper scripts for easy management and manual testing.

- **Installation:** Execute `./install.sh`. This script creates the Python virtual environment, installs dependencies, and configures an hourly systemd user timer.
- **Automated Execution:** Handled automatically by the systemd service (`skroutz-scraper.timer`).
- **Service Management:** Use `./scripts/disable.sh` to temporarily stop and disable the background timer, `./scripts/enable.sh` to resume it, and `./scripts/stop.sh` to forcefully kill a running execution.
- **Manual Execution:** Execute `./scripts/run.sh` to run the scraper interactively and view output logs in the terminal.
- **Help Message:** Execute `./scripts/run.sh --help` to print the help message and view all available script arguments.
- **Testing Notifications:** Run `./scripts/run.sh --ping` to send a test payload and verify that the Apprise URLs in your `.env` file are configured correctly.
- **Health Checks:** Run `./scripts/run.sh --status` to perform a comprehensive health check. This validates the configuration (products and notification settings), checks for available script updates, and verifies the status of the background systemd service and timer.
- **Uninstallation:** Execute `./scripts/uninstall.sh` to cleanly stop and disable the systemd services and remove the virtual environment (user data is preserved).
- **Exit Codes:** The script utilizes specific exit codes to indicate failure states when running as a service (these can be easily viewed using the `--status` flag):
  - **`15`**: Indicates an issue with the `config/skroutz.json` file (e.g., file missing, wrong permissions, or invalid JSON).
  - **`16`**: Indicates an issue with the `.env` file configuration.
  - **`17`**: Indicates the scraper was blocked by the server due to rate limits.
  - **`42`**: Indicates that a specific scraper target did not start because another instance of it is already running (file lock timeout).
  - **`130`**: Indicates that the script was interrupted (e.g., via Ctrl+C or system termination).

## Development Conventions
- **Scraping Practices & Rate Limiting:** The scraper intentionally paces requests using a base delay (20s) plus randomized jitter (1-5s) between product checks to avoid triggering Skroutz's anti-bot protections. Concurrency is avoided to maintain a low profile.
- **Data Integrity:** Updates to the `config/skroutz.json` file (such as logging the latest price and check timestamp) are performed using an atomic save mechanism to prevent file corruption in case of unexpected interruptions.
- **Error Handling & Logging:** When running silently in the background, exceptions are caught and logged to `logs/errors.txt`. If critical errors occur (like repeated scraping failures or a total crash), the script utilizes the Apprise notifier to alert the user of the failure.
- **Code Style:** Standard Python object-oriented practices are used with a focus on the Single Responsibility Principle, Dependency Injection, and the Open/Closed Principle. Logic is strictly separated into focused modules. Adding support for new stores requires creating a new plugin package under `scrapers/` implementing `BasePlugin`, `BaseScraperClient`, `BaseTrackedItem`, and `BaseDataManager` — no existing files need to be modified. Configuration and state are decoupled from the main execution logic.