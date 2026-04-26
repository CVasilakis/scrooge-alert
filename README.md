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

    The `install.sh` script will automatically create a Python virtual environment, install the required dependencies, and set up an hourly systemd user timer pointing to the script wrapper.

4. **Configure your settings:**

    ```sh
    cp .env.example .env
    nano .env

    cp data/products.json.example data/products.json
    nano data/products.json
    ```

    For more information regarding your [Push Notification Settings](#file-1-notification-settings-env) and your [Product Tracking List](#file-2-product-tracking-dataproductsjson) proceed to the [Configuration](#%EF%B8%8F-configuration) section.

> [!NOTE]  
> If you encounter any issues during installation or setup, please refer to the [Troubleshooting & Debugging](#-troubleshooting--debugging) section. If your problem persists, feel free to [open an issue](https://github.com/CVasilakis/skroutz-price-alert/issues).

## ⚙️ Configuration

All custom user parameters reside outside the source code logic. Apprise Notification URLs go in the `.env` file, and the Skroutz products you want to monitor go inside the `data/products.json` file.

### File 1: Notification Settings (`.env`)

The script uses the popular [Apprise library](https://github.com/caronc/apprise) to push notifications to almost any major platform (Discord, Telegram, Slack, Email, etc.). Check the [Apprise Supported Services Documentation](https://appriseit.com/services/) to learn how to format your notification URL. Alternatively, you can use this handy [URL Builder Tool](https://appriseit.com/tools/url-builder/) to generate your string easily.

```sh
cp .env.example .env
nano .env
```

Start by making a copy of the provided example template. Then edit the `.env` file to configure the `NOTIFICATION_URLS` variable (you can separate multiple platforms with commas). Here is an example to receive Telegram and Discord notifications simultaneously:

```env
NOTIFICATION_URLS = tgram://<token>/<chat_id>, discord://<webhook_id>/<webhook_token>
```

### File 2: Product Tracking (`data/products.json`)
The `data/` directory contains all your product tracking data.

```sh
cp data/products.json.example data/products.json
nano data/products.json
```

Create your tracking file from the provided template. Then, edit the `data/products.json` file to add the products you wish to monitor:

```json
{
  "products": [
    {
      "productName": "Awesome Monitor",
      "url": "https://www.skroutz.gr/s/xxxxxxxx/product_url.html",
      "targetPrice": 150
    },
    {
      "productName": "Great Game",
      "url": "https://www.skroutz.cy/s/xxxxxxxx/product_url.html",
      "targetPrice": 30
    }
  ]
}
```

#### Supported Fields:
| Field | Type | Source | Description |
| :--- | :--- | :--- | :--- |
| `productName` | String | **User-defined** | A friendly naming label used inside the notifications. |
| `url` | String | **User-defined** | The direct link to the Skroutz product page. |
| `targetPrice` | String/Number | **User-defined** | The maximum price threshold. If the price drops below this, you get alerted. |
| `skip` | Boolean | **User-defined** | Optional. Set to `true` to skip monitoring this product. Defaults to `false`. |
| `last_price` | Number | *Internal* | Auto-generated by the script. Do not modify. Stores the latest scraped down price. |
| `last_successful_check`| String | *Internal* | Auto-generated by the script. Do not modify. Timestamp of the time the product was last successfully verified. |

> [!NOTE]
> You do not need to manually add the internal fields. The script will generate and maintain them during execution.

## 💻 Usage

There are two ways to execute the script: automatically via the scheduled systemd timer, or manually for testing.

### Option 1: Automated Run

Once `install.sh` has run successfully, the script executes automatically via a systemd timer every hour. The systemd timer applies a randomized up-to-60s startup delay before launching the execution wrapper (`scripts/run_scraper.sh`) to simulate human timing and avoid exact scheduling footprints.

### Option 2: Manual Run (CLI Flags)

You can manually interact with the application using the wrapper script. The wrapper safely loads the virtual environment and passes commands along to the backend application.

```sh
./scripts/run_scraper.sh [FLAGS]
```

#### Available CLI Flags:

| Flag | Action |
| :--- | :--- |
| `--silent` | Suppresses all console output. This is automatically used by the systemd setup to prevent unnecessary log spam. |
| `--test-notification` | Sends a test payload directly to your configured Apprise URLs, then immediately exits. Helps pinpoint `.env` misconfigurations. |

If you run the script without any flags, it will execute normally and output its progress logs directly to the terminal. You can safely interrupt the manual execution at any time by pressing `Ctrl+C`.

```sh
./scripts/run_scraper.sh
```

> [!TIP]
> If the script fails to run in the background or you do not receive expected notifications, please consult the [Troubleshooting & Debugging](#-troubleshooting--debugging) section. If your problem persists, feel free to [open an issue](https://github.com/CVasilakis/skroutz-price-alert/issues).

## 🔔 Notifications & Messages

You might receive the following push notification alerts throughout the lifecycle of the script:

| Notification Title | Body / Cause |
| :--- | :--- |
| **Skroutz Price Drop Alert! 📉** | `"{Product} found at a price below {target} {currency}..."` <br> Sent when an item's requested price successfully matches your price limit. |
| **Skroutz Tracking Stale ⚠️** | `"Link {url} has not been updated for 24 hours..."` <br> Sent if a specific Skroutz URL continuously fails the scrape. |
| **Skroutz Scraping Errors 🛑** | `"Skroutz Price Alert Script encountered errors on some products..."` <br> Sent if the application hits fatal request limits or unhandled exceptions. |
| **Skroutz Script Crash 💥** | `"Skroutz Price Alert Script failed. Check error log."` <br> Sent if the system completely failed to run. |

## 🗑️ Uninstallation

To completely remove the background service and clean up the python virtual environment, you can run the uninstall script:

```sh
chmod +x uninstall.sh
./uninstall.sh
```

The `uninstall.sh` script will safely:
* Stop and disable the systemd scheduled timer and service.
* Remove the systemd configuration files.
* Delete the Python virtual environment (`venv`).

> [!NOTE]
> Your user configurations, specifically the `.env` and `data/products.json` files, are purposefully **not** removed by the `uninstall.sh` script in case you are migrating or updating. If you intend to completely purge the application, just delete the `skroutz-price-alert` directory after running the uninstall script.

## 🔧 Troubleshooting & Debugging

**1. Failing to Fetch Products:**

If the script cannot retrieve data for certain items, first check for broken links. Ensure the URL in your `data/products.json` is correct and the product page is still active on the platform.

If your links are valid but multiple products fail consistently, the website's anti-bot protection has likely blocked your connection temporarily. To resolve this, remove less important products to reduce your network traffic, or decrease how often the script runs by editing your background schedule (`~/.config/systemd/user/skroutz-price-alert.timer`).

> [!TIP]  
> For the best results, this script should **not** be run behind a VPN and should ideally be executed from a standard Greek residential IP address. High traffic coming from known VPS providers, data centers, or VPNs is very likely to trigger strict anti-bot mechanisms, causing the script to fail.

**2. Not Receiving Notifications:**

You can easily test your notification setup by running the script with a test flag:

```sh
./scripts/run_scraper.sh --test-notification
```

If you do not receive a test message, carefully review the [Notification Settings](#file-1-notification-settings-env) section and verify that your Apprise URL inside the `.env` file is formatted correctly.

**3. Finding Crash Reports (Error Logs):**

If the script unexpectedly fails while running in the background, it saves the error details directly to a log file. You can view these tracebacks by running:

```sh
cat data/error_log.txt
```

**4. Verifying the Background Service:**

To confirm that the script is properly scheduled and running in the background, check the status of your systemd timer (the scheduler):

```sh
systemctl --user status skroutz-price-alert.timer
```
*(A healthy setup will display `enabled` and `active (waiting)` in green).*

Next, check the status of the service itself:

```sh
systemctl --user status skroutz-price-alert.service
```
*(You should see a green indicator showing `TriggeredBy: ● skroutz-price-alert.timer`).*

If either of these commands reveals an error or a failed status, please [open an issue](https://github.com/CVasilakis/skroutz-price-alert/issues).

## ⚖️ Rate Limiting

The default configuration applies rate limiting to reduce traffic and increase the success rate of the web scraper:

*   A randomized startup delay (up to 60 seconds) is applied by the systemd timer before each background execution to avoid exact scheduling footprints.
*   Products are checked sequentially, not concurrently.
*   A base 20s delay, plus randomized jitter (1-5s), is enforced between requests.

> [!TIP]
> Periodically remove items from `products.json` once you purchase them or abandon interest. Also avoid decreasing the scraping delays. Over-frequent scraping will trigger strict anti-bot mechanisms and the script will fail to fetch the product data.

## ❓ Frequently Asked Questions

**1. How can I tell if the script is actively running in the background?**

The easiest way to verify is to open your `data/products.json` file. The script automatically updates the `last_successful_check` timestamp for each product every time it runs. If those timestamps are recent, the script is doing its job! You can also manually check the background service and logs as described in the [Troubleshooting & Debugging](#-troubleshooting--debugging) section.

**2. Can I get notifications sent to Discord, Telegram, or other specific services?**

Most likely, yes! The script uses the [Apprise](https://github.com/caronc/apprise) push notification library, which supports almost every major platform available. As long as you can format your target service as an Apprise URL inside your `.env` file, it will work perfectly. Check out their [Supported Services](https://appriseit.com/services/) page for the full list.

**3. How do I update the script to the latest version?**

Navigate to the project directory and pull the latest changes using Git. Afterward, run the installation script again to ensure any new dependencies are installed and your environment is properly updated:

```sh
git pull
./install.sh
```

**4. Is it safe to edit my product list while the script is running?**

Absolutely. You can safely add, edit, or remove products at any time. The script uses an atomic save mechanism, meaning your changes will be safely preserved and seamlessly picked up during the next scheduled execution cycle without causing any file conflicts.

**5. How many products can I track at once using the default settings?**

Because the script intentionally pauses for about 25 seconds per product to avoid being blocked by the website, monitoring too many items might cause the execution to exceed the 60-minute window before the next cycle starts. While the script has safety locks to prevent overlapping runs, a practical soft limit is around **100 products** per instance when using the default hourly schedule.

**6. How long does a full scrape take to complete?**

To mimic human behavior, the script spaces out its requests. It applies a base delay of 20 seconds per product, plus an unpredictable jitter of 1–5 seconds. If you are tracking 10 products in the background, a full run will take approximately **4 to 6 minutes**. *(Note: Background runs via systemd also have a randomized startup delay of up to 60 seconds, so manual runs will finish slightly faster).*

**7. Why are the timestamps in my product list showing the wrong time?**

The script relies entirely on your system's clock to generate the timestamps saved in `products.json`. If the time looks wrong, your operating system's clock or timezone is likely out of sync. You can usually fix this by updating your server's time settings.

**8. How do I move the project to a different folder?**

Python virtual environments break if you simply drag and drop them to a new location. To safely move the project:

1. Run `./uninstall.sh` in the old folder to clean up the existing background processes.
2. Clone the repository into your new desired folder using Git.
3. Move your `data/products.json` and `.env` files from the old folder to the new one.
4. Run `./install.sh` in the new location to rebuild the environment and background timers.
5. Safely delete the old project folder.

**9. What is systemd "lingering," and why does the installer enable it?**

By default, Linux kills all background processes associated with a user the moment they log out of their SSH session. Enabling "lingering" (usually via `loginctl enable-linger`) tells the system to keep your user's background services running continuously, even after you disconnect. It is a completely safe, standard Linux feature that allows the scraper to run automatically without requiring root (`sudo`) privileges. The installer simply checks if it's enabled for your user and turns it on if it isn't, and because other services might rely on this system-wide setting, the uninstallation script intentionally leaves it enabled.

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
