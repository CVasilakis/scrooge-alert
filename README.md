<h1 align="center">
  <img src="assets/banner.svg" alt="Project Banner" width="120"><br>
  Skroutz Price Alert
</h1>

<p align="center">An open-source Skroutz web scraper and price monitor. Receive automated push notifications when products reach your desired price.</p>


> [!IMPORTANT]
> Skroutz is a registered trademark of Skroutz S.A. This project is an independent, unofficial tool and is not affiliated with, authorized, maintained, sponsored, or endorsed by Skroutz S.A. in any way.

## 📑 Table of Contents

<details>
  <summary><b>Click to expand</b></summary>
  <br>

1. [Features](#-features)
2. [Supported Domains](#-supported-domains)
3. [Prerequisites](#-prerequisites)
4. [Installation](#-installation)
5. [Configuration](#%EF%B8%8F-configuration)
   - [Notification Settings (.env)](#file-1-notification-settings-env)
   - [Product Tracking (data/products.json)](#file-2-product-tracking-dataproductsjson)
6. [Usage](#-usage)
   - [Automated Systemd Run](#option-1-automated-run)
   - [Manual Run (CLI Flags)](#option-2-manual-run-cli-flags)
7. [Notifications & Messages](#-notifications--messages)
8. [Uninstallation](#%EF%B8%8F-uninstallation)
9. [Troubleshooting & Debugging](#-troubleshooting--debugging)
10. [Rate Limiting](#%EF%B8%8F-rate-limiting)
11. [Frequently Asked Questions (FAQ)](#-frequently-asked-questions)
12. [Future Updates (Roadmap)](#%EF%B8%8F-future-updates-roadmap)
13. [Contributing & Issues](#-contributing--issues)
14. [Support & Donations](#-support--donations)
15. [Disclaimer](#%EF%B8%8F-disclaimer)
16. [License](#-license)

</details>

## ✨ Features

* **Automated Monitoring:** Set it and forget it. Tracks products silently in the background.
* **Instant Notifications:** Get instant push notifications (Telegram, Discord, Slack, Email, etc.) for price drops.
* **Custom Target Prices:** Define specific price drop thresholds for every individual product.

## 🌍 Supported Domains
The scraper supports all Skroutz domains, dynamically detecting the locale and currency:

* `.gr` (Greece - €)
* `.cy` (Cyprus - €)
* `.bg` (Bulgaria - €)
* `.de` (Germany - €)
* `.ro` (Romania - Lei)

## 📋 Prerequisites

*   Linux/Unix environment (`systemd` available for scheduling).
*   Python 3.7+ installed (`python3`, `python3-venv`).

## 🚀 Installation

1. **Install required system packages:**

    <details open>
    <summary><b>Debian / Ubuntu / Raspberry Pi OS / Linux Mint</b></summary>
    <br>

    ```sh
    sudo apt update
    sudo apt install git python3-venv
    ```
    </details>

    <details>
    <summary><b>Fedora / RHEL / Rocky Linux</b></summary>
    <br>

    ```sh
    sudo dnf install git python3
    ```
    </details>

    <details>
    <summary><b>Arch Linux / Manjaro</b></summary>
    <br>

    ```sh
    sudo pacman -S git python
    ```
    </details>

2. **Clone the repository:**

    ```sh
    git clone https://github.com/CVasilakis/skroutz-price-alert
    cd skroutz-price-alert
    ```

3. **Run the installation script:**

    ```sh
    chmod +x install.sh
    ./install.sh
    ```

    The `install.sh` script will automatically create a Python virtual environment, install the required dependencies, and set up an hourly systemd user timer pointing to the script wrapper. No `sudo` or elevated privileges are required for the installation.

4. **Configure your settings:**

    Proceed to the [Configuration](#%EF%B8%8F-configuration) section for more information regarding your [Push Notification Settings](#file-1-notification-settings-env) and your [Product Tracking List](#file-2-product-tracking-dataproductsjson)

## ⚙️ Configuration

All custom user parameters reside outside the source code logic. Apprise Notification URLs go in the `.env` file, and the Skroutz products you want to monitor go inside the `data/products.json` file.

### File 1: Notification Settings (`.env`)

This script leverages the [Apprise library](https://github.com/caronc/apprise) to deliver push notifications across numerous platforms, including Discord, Telegram, Slack, and Email. To format your specific Apprise URL, consult the [Apprise Supported Services Documentation](https://appriseit.com/services/) or use their interactive [URL Builder Tool](https://appriseit.com/tools/url-builder/). Copy the provided `.env.example` template to a new `.env` file and configure the `NOTIFICATION_URLS` variable:

```sh
cp .env.example .env
nano .env
```

You can specify multiple platforms by separating their URLs with commas. For instance, to receive alerts on both Telegram and Discord simultaneously, your `.env` file would look like this:

```env
NOTIFICATION_URLS = tgram://<token>/<chat_id>, discord://<webhook_id>/<webhook_token>
```

### File 2: Product Tracking (`data/products.json`)

The `data/` directory stores your product monitoring list. Copy the provided `data/products.json.example` template to create your initial tracking file:

```sh
cp data/products.json.example data/products.json
nano data/products.json
```

Afterwards, open `data/products.json` and populate it with the items you want to keep an eye on. For example, if you wish to track two products, your file should be structured like this:

```json
{
  "products": [
    {
      "name": "Awesome Monitor",
      "url": "https://www.skroutz.gr/s/xxxxxxxx/product_url.html",
      "target_price": 150
    },
    {
      "name": "Great Game",
      "url": "https://www.skroutz.cy/s/xxxxxxxx/product_url.html",
      "target_price": 30
    }
  ]
}
```

#### Supported Fields:
| Field | Type | Source | Description |
| :--- | :--- | :--- | :--- |
| `name` | String | **User-defined** | A friendly naming label used inside the notifications. |
| `url` | String | **User-defined** | The direct link to the Skroutz product page. |
| `target_price` | String/Number | **User-defined** | The maximum price threshold. If the price drops below this, you get alerted. |
| `skip` | Boolean | **User-defined** | Optional. Set to `true` to skip monitoring this product. Defaults to `false`. |
| `last_price` | Number | *Internal* | Auto-generated by the script. Do not modify. Stores the latest scraped down price. |
| `last_checked`| String | *Internal* | Auto-generated by the script. Do not modify. Timestamp of the last successful price check. |

> [!NOTE]
> You do not need to manually add the internal fields. The script will generate and maintain them during execution.

## 💻 Usage

There are two ways to execute the script: automatically via the scheduled systemd timer, or manually for testing.

### Option 1: Automated Run

Once `install.sh` has run successfully, the script executes automatically via a systemd timer every hour. The systemd timer applies a randomized up-to-5m startup delay before launching the execution wrapper (`scripts/run.sh`) to simulate human timing and avoid exact scheduling footprints.

### Option 2: Manual Run (CLI Flags)

You can manually interact with the application using the wrapper script. The wrapper safely loads the virtual environment and passes commands along to the backend application.

```sh
./scripts/run.sh [FLAGS]
```

#### Available CLI Flags:

| Flag&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; | Action |
| :--- | :--- |
| `--quiet` | Suppresses all console output. This is used by the systemd setup to prevent log spam. |
| `--status` | Performs a comprehensive health check. It validates the configuration, and verifies the background systemd service and timer status. |
| `--ping` | Sends a test notification directly to your configured Apprise URLs, then immediately exits. Helps pinpoint `.env` misconfigurations. |

#### Normal Execution:

If you run the script without any flags, it will execute normally and output its progress logs directly to the terminal. You can safely interrupt the manual execution at any time by pressing `Ctrl+C`.

```sh
./scripts/run.sh
```

> [!NOTE]
> Only one instance of the script is allowed to run at a time to avoid triggering anti-bot protections. If a background execution is currently in progress, your manual run will be blocked until it completes. If you need to forcefully stop the active background execution to run the script manually, you can safely use the command `systemctl --user stop skroutz-price-alert.service`. This stops the current background run but will not break any future scheduled executions.

#### Status Check:

If you run the script using the `--status` flag, the script verifies the integrity of your `data/products.json` file, validates your environment variables in `.env` file, and queries systemd to display the following background execution details:

```sh
./scripts/run.sh --status
```

- **Linger Enabled:** Checks if user lingering is configured for background execution.
- **Systemd Timer Active:** Shows whether the timer is currently active.
- **Last Execution Time:** Displays when the script was last run.
- **Last Execution Status:** Indicates last execution results and if any errors happened.
- **Next Scheduled Execution:** Displays the next scheduled run or if it's currently running.

#### Test Notifications:

If you want to test whether your `.env` notification URLs are configured correctly without waiting for a scheduled run or a real price drop, you can use the `--ping` flag.

```sh
./scripts/run.sh --ping
```

This will send a test message to each configured service. It will output a report of successes and failures, helping you quickly identify and debug any misconfigured notification endpoints.

> [!TIP]
> If the script fails to run in the background or you do not receive expected notifications, please consult the [Troubleshooting & Debugging](#-troubleshooting--debugging) section. If your problem persists, feel free to [open an issue](https://github.com/CVasilakis/skroutz-price-alert/issues).

## 🔔 Notifications & Messages

You might receive the following push notification alerts throughout the lifecycle of the script:

| Notification Title | Body / Cause |
| :--- | :--- |
| **Skroutz Price Drop Alert!** | `"{Product} is now available for ..."` <br> Sent when a product's price falls below your price limit. |
| **Skroutz Tracking Stale** | `"The scraping for "{Product}" hasn't been successfully completed in over 48 hours..."` <br> Sent if a specific product continuously fails the scrape. |
| **Skroutz Scraping Errors** | `"The Skroutz Price Alert script encountered errors while checking some of your products..."` <br> Sent if the application hits fatal request limits or unhandled exceptions. |
| **Skroutz Script Crash** | `"The Skroutz Price Alert script failed unexpectedly. Please review the error logs..."` <br> Sent if the script completely failed to run. |
| **Skroutz Test Notification** | `"This is a test message to confirm that your Skroutz Price Alert notifications are configured correctly!"` <br> Sent when manually invoking the script with the `--ping` flag. |

## 🗑️ Uninstallation

To completely remove the background service and clean up the Python virtual environment, execute the uninstallation script:

```sh
./uninstall.sh
```

The uninstallation process safely performs the following actions:
* Stops and disables the systemd scheduled timer and service.
* Removes the associated systemd configuration files.
* Deletes the Python virtual environment (`venv`).

> [!NOTE]
> **User Data:** Your personal configurations, specifically the `.env` and `data/products.json` files, are preserved by the uninstallation script to prevent accidental data loss. If you wish to completely purge the application, simply delete the `skroutz-price-alert` directory after running the uninstallation script.
> 
> **User Lingering:** The script purposefully leaves systemd user lingering enabled, as other background services on your system may rely on it. If you are certain that no other services require this functionality, you can manually disable it by running: `loginctl disable-linger $USER`

## 🔧 Troubleshooting & Debugging

**1. Failing to Fetch Products:**

If the script cannot retrieve data for certain items, begin by checking for broken links in your `data/products.json` file. Invalid URLs are often redirected to similar products by Skroutz.
If the URLs are correct but failures persist across multiple products, your connection has likely been temporarily restricted by the website's anti-bot protection. To mitigate this, reduce your network traffic by tracking fewer products, or decrease the script's run frequency by editing `~/.config/systemd/user/skroutz-price-alert.timer`.

> [!TIP]  
> For the best results, this script should **not** be run behind a VPN and should ideally be executed from a standard Greek residential IP address. High traffic coming from known VPS providers, data centers, or VPNs is very likely to trigger strict anti-bot mechanisms, causing the script to fail.

**2. Not Receiving Notifications:**

If you do not receive a test message, carefully review the [Notification Settings](#file-1-notification-settings-env) section and verify that your Apprise URLs inside the `.env` file are formatted correctly.
You can easily test your notification setup using the `--ping` flag:

```sh
./scripts/run.sh --ping
```

**3. Finding Crash Reports (Error Logs):**

If the script unexpectedly fails while running in the background, it saves the error details directly to the `data/error_log.txt` file.

## ⚖️ Rate Limiting

The default configuration applies rate limiting to reduce traffic and increase the success rate of the web scraper:

*   A randomized startup delay (up to 5 minutes) is applied by the systemd timer before each background execution to avoid exact scheduling footprints.
*   Products are checked sequentially, not concurrently.
*   A base 20s delay, plus randomized jitter (1-5s), is enforced between requests.

> [!TIP]
> Periodically remove items from `data/products.json` once you purchase them or abandon interest. Also avoid decreasing the scraping delays. Over-frequent scraping will trigger strict anti-bot mechanisms and the script will fail to fetch the product data.

## ❓ Frequently Asked Questions

<details open>
<summary><b>1. How can I tell if the script is actively running in the background?</b></summary>
<br>

To confirm the script is running in the background, use the `--status` flag. If the script reports no errors, you can be sure it is configured correctly and running in the background:

```sh
./scripts/run.sh --status
```

The systemd execution metrics reported by the `--status` flag only reflect background scheduled executions, not manual runs.
If the command reveals any warnings, please run `./update.sh` which re-installs the background service and ensures that you are on the latest version. If the issue persists after updating, please [open an issue](https://github.com/CVasilakis/skroutz-price-alert/issues) for further assistance.
</details>

<details>
<summary><b>2. Can I get notifications sent to Discord, Telegram, or other specific services?</b></summary>
<br>

Most likely, yes! The script uses the [Apprise](https://github.com/caronc/apprise) push notification library, which supports almost every major platform available. As long as you can format your target service as an Apprise URL inside your `.env` file, it will work perfectly. Check out their [Supported Services](https://appriseit.com/services/) page for the full list.
</details>

<details>
<summary><b>3. How do I update the script to the latest version?</b></summary>
<br>

Navigate to the project directory and run the update script. This will pull the latest changes using Git and automatically run the installation script again to ensure any new dependencies are installed and your environment is properly updated:

```sh
./update.sh
```

When run manually, the script automatically checks the online repository for updates. If a newer version is found, a message is displayed in the terminal.
</details>

<details>
<summary><b>4. Is it safe to edit my product list while the script is running?</b></summary>
<br>

Absolutely. You can safely add, edit, or remove products at any time. The script uses an atomic save mechanism, meaning your changes will be safely preserved and seamlessly picked up during the next scheduled execution cycle without causing any file conflicts.
</details>

<details>
<summary><b>5. How many products can I track at once using the default settings?</b></summary>
<br>

Because the script intentionally pauses for about 25 seconds per product to avoid being blocked by the website, monitoring too many items might cause the execution to exceed the 60-minute window before the next cycle starts. While the script has safety locks to prevent overlapping runs, a practical soft limit is around **100 products** per instance when using the default hourly schedule.
</details>

<details>
<summary><b>6. How long does a full scrape take to complete?</b></summary>
<br>

To mimic human behavior, the script spaces out its requests. It applies a base delay of 20 seconds per product, plus an unpredictable jitter of 1–5 seconds. If you are tracking 10 products, a full manual run will take approximately 4 minutes. *(Note: Background runs via systemd also have a randomized startup delay of up to 5 minutes, which is not applied to manual executions).*
</details>

<details>
<summary><b>7. Why are the timestamps in my product list showing the wrong time?</b></summary>
<br>

The script relies entirely on your system's clock to generate the timestamps saved in `data/products.json`. If the time looks wrong, your operating system's clock or timezone is likely out of sync. You can usually fix this by updating your server's time settings.
</details>

<details>
<summary><b>8. How do I move the project to a different folder?</b></summary>
<br>

1. Run `./uninstall.sh` in the old folder to clean up the existing background processes.
2. Clone the repository into your new desired folder using Git.
3. Move your `data/products.json` and `.env` files from the old folder to the new one.
4. Run `./install.sh` in the new location to rebuild the environment and background timers.
5. Safely delete the old project folder.
</details>

<details>
<summary><b>9. What is systemd "lingering," and why does the installer enable it?</b></summary>
<br>

By default, Linux kills all background processes associated with a user the moment they log out of their SSH session. Enabling "lingering" tells the system to keep your user's background services running continuously, even after you disconnect. It is a completely safe, standard Linux feature that allows the scraper to run automatically without requiring root (`sudo`) privileges. The installer simply checks if it's enabled for your user and turns it on if it isn't, and because other services might rely on this setting, the uninstallation script intentionally leaves it enabled.
</details>

## 🗺️ Future Updates (Roadmap)

- [x] **Enhanced Evasion:** Rotate TLS sessions and request fingerprints intelligently.
- [ ] **User Interface:** Introduction of a Web UI for non-CLI management.
- [ ] **Docker Support:** Add an alternative Dockerized setup via docker-compose configuration.

To see all the undergoing feature requests or to request a new feature, please check the [open issues](https://github.com/CVasilakis/skroutz-price-alert/issues).

## 🤝 Contributing & Issues

Contributions are always welcome! If you have an idea to make this project better, feel free to fork the repository and submit a pull request.
If you encounter a bug or run into any issues, please [open an issue](https://github.com/CVasilakis/skroutz-price-alert/issues). To help me resolve it quickly, include as much detail as possible.

## 💝 Support & Donations

Did this project save you time or help you snag a deal? Leaving a ⭐ on the repository means a lot! If you'd like to further support my work, consider buying me a coffee. Thanks!

<p align="left">
  <a href="https://www.paypal.com/donate/?hosted_button_id=EQ4BXMGA2R544">
    <img src="assets/qrcode.svg" alt="Donation QR Code" width="150">
  </a>
</p>

## ⚠️ Disclaimer

Please use this script responsibly. This script is intended for personal, educational use. Users are solely responsible for how they use the script and must comply with Skroutz's Terms of Service. The author is not responsible for any bans, blocks, or legal issues that may arise from using this software.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
