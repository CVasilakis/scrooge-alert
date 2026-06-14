# Scrooge Alert - Development Context

## Project Overview
This project is an automated Python application designed to monitor product prices across Skroutz domains and send push notifications when prices drop below user-defined target thresholds. 

- **Main Technologies:** Python 3, `apprise` (for versatile push notifications via Telegram, Discord, etc.), `tls_client` (for evasive web scraping by mimicking browser TLS fingerprints), and systemd (for automated background scheduling on Linux).
- **Architecture:** The application features a modular, plugin-based architecture residing in `src/core/`. The entrypoint is `main.py`, which delegates to specialized modules:
  - **Scrapers (`scrapers/`)**: Self-contained plugin packages grouped by target store. Each plugin (e.g. `scrapers/skroutz/`) contains its own client, model, storage, and a `plugin.py` descriptor that acts as the single source of truth for domains, config filenames, and class bindings.
    - **Base Contracts (`scrapers/base/`)**: Abstract base classes (`BaseScraperClient`, `BaseTrackedItem`, `ScrapeResult`, `BaseDataManager`, `BasePlugin`) defining the interfaces all plugins must implement.
    - **Registry (`scrapers/registry.py`)**: A unified `ScraperRegistry` that replaces the old separate `ScraperFactory` and `DataManagerFactory`. Handles URL-to-plugin resolution, lazy client/manager instantiation, and auto-discovery of plugins via `pkgutil`.
  - **Orchestration (`orchestrator.py`)**: `ScrapingOrchestrator` runs a store-agnostic execution loop over targets and products, handling per-target file locks (`locks.py`), retries, and notification dispatch.
  - **Notifications (`notifier.py`)**: Apprise wrapper; used both for price-drop alerts and to notify the user of critical failures.
  - **Configuration & Validation (`constants.py`, `utils.py`)**: Centralized constants and environment/file health checks.
  - **Terminal UI (`tui.py`)**: Manages the interactive progress bar during sleep intervals using the Strategy pattern (`ExecutionStrategy`): `InteractiveExecutionStrategy` renders the Rich progress bar; `SilentExecutionStrategy` is used with `--quiet` (and by the systemd service).
  - **CLI Tools (`ping.py`, `status.py`)**: Dedicated scripts for specific CLI commands to maintain separation of concerns.
  User configuration is completely externalized to `.env` (`NOTIFICATION_URLS`, comma-separated Apprise URLs) and one `config/<plugin>.json` per scraper (e.g. `config/skroutz.json` for the list of tracked products; the filename comes from the plugin descriptor). The JSON config also doubles as state: the scraper writes the latest price and check timestamp back into it. The application is designed to run silently as a background task, leveraging a local Python virtual environment (`venv`) to isolate dependencies.

## Building and Running
The application is primarily intended for automated background execution but provides wrapper scripts for easy management and manual testing. There is no test suite or linter configured. All execution goes through the venv (`./venv/bin/python3`); the wrapper scripts handle this for you.

- **Installation:** Execute `./install.sh`. This script creates the Python virtual environment, installs dependencies from `requirements.txt`, and configures an hourly systemd user timer.
- **Automated Execution:** Handled automatically by the systemd service (`skroutz-scraper.timer`).
- **Service Management:** Use `./scripts/disable.sh` to temporarily stop and disable the background timer, `./scripts/enable.sh` to resume it, and `./scripts/stop.sh` to forcefully kill a running execution. `./update.sh` (repo root) updates the installation.
- **Manual Execution:** Execute `./scripts/run.sh` to run the scraper interactively and view output logs in the terminal. Flags: `--quiet` (no console output) and one dynamically generated flag per registered plugin (e.g. `--skroutz`) to run only that scraper. The `--ping` and `--status` flags must be used alone.
- **Direct Invocation:** `./venv/bin/python3 src/core/main.py` — note that `main.py` inserts `src/core/` into `sys.path`, so all intra-project imports are written relative to `src/core/` (e.g. `from scrapers.registry import ...`), not `src.core.scrapers...`.
- **Help Message:** Execute `./scripts/run.sh --help` to print the help message and view all available script arguments.
- **Testing Notifications:** Run `./scripts/run.sh --ping` to send a test payload and verify that the Apprise URLs in your `.env` file are configured correctly.
- **Health Checks:** Run `./scripts/run.sh --status` to perform a comprehensive health check. This validates the configuration (products and notification settings), checks for available script updates, and verifies the status of the background systemd service and timer.
- **Uninstallation:** Execute `./scripts/uninstall.sh` to cleanly stop and disable the systemd services and remove the virtual environment (user data is preserved).
- **Exit Codes:** The script utilizes specific exit codes to indicate failure states when running as a service (these can be easily viewed using the `--status` flag):
  - **`15`**: Indicates an issue with a plugin's products config file, e.g. `config/skroutz.json` (file missing, wrong permissions, or invalid JSON).
  - **`16`**: Indicates an issue with the `.env` file configuration.
  - **`17`**: Indicates the scraper was blocked by the server due to rate limits.
  - **`42`**: Indicates that a specific scraper target did not start because another instance of it is already running (file lock timeout).
  - **`130`**: Indicates that the script was interrupted (e.g., via Ctrl+C or system termination).

## Development Conventions
- **Scraping Practices & Rate Limiting:** The scraper intentionally paces requests using a base delay (20s) plus randomized jitter (1-5s) between product checks to avoid triggering Skroutz's anti-bot protections. Concurrency is avoided to maintain a low profile. Do not "optimize" this away.
- **Data Integrity:** Updates to the `config/*.json` files (such as logging the latest price and check timestamp) must go through the existing atomic save mechanism to prevent file corruption in case of unexpected interruptions.
- **Error Handling & Logging:** When running silently in the background, exceptions are caught and logged to `logs/errors.txt`. If critical errors occur (like repeated scraping failures or a total crash), the script utilizes the Apprise notifier to alert the user of the failure.
- **Code Style:** Standard Python object-oriented practices are used with a focus on the Single Responsibility Principle, Dependency Injection, and the Open/Closed Principle. Logic is strictly separated into focused modules. Adding support for new stores requires creating a new plugin package under `scrapers/` implementing `BasePlugin`, `BaseScraperClient`, `BaseTrackedItem`, and `BaseDataManager` — no existing files need to be modified. Configuration and state are decoupled from the main execution logic.
