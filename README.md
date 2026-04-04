<h1 align="center">
  <img src="assets/banner.svg" alt="Project Banner" width="120"><br>
  Skroutz Price Alert
</h1>

<p align="center">Get notified via push notification when a product on Skroutz drops below your target price.</p>

> [!IMPORTANT]
> Skroutz is a registered trademark of Skroutz S.A. This project is an independent, unofficial tool and is not affiliated with, authorized, maintained, sponsored, or endorsed by Skroutz S.A. in any way.

## ✨ Features

*   **Automated Monitoring:** Set it and forget it. Tracks products silently in the background.
*   **Custom Target Prices:** Define specific price drop thresholds for every individual item.
*   **Smart Notifications:** Get instant alerts via [Apprise](https://github.com/caronc/apprise) (Telegram, Discord, etc.) for price drops or errors.
*   **Anti-Bot Evasion:** Safely fetches data using realistic browser fingerprints and randomized delays to avoid blocks.

## 📋 Prerequisites

*   Linux/Unix environment.
*   Python 3 installed.
*   crontab available for scheduling.

## 🚀 Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/CVasilakis/skroutz-price-alert
    cd skroutz-price-alert
    ```

2.  **Install needed packages**
    ```bash
    sudo apt update
    sudo apt install python3-venv
    ```

3.  **Run the installation script:**
    ```bash
    chmod +x install.sh
    ./install.sh
    ```
    The `install.sh` script will automatically:
    *   Create a Python virtual environment.
    *   Install required dependencies.
    *   Set up an hourly cron job.
    *   Safely update existing installations (safe to run multiple times).

## ⚙️ Configuration

Before running the script, you need to configure the products to monitor and notification settings in `config.json`.

```json
{
  "notification": {
    "telegram": "tgram://<bot_token>/<chat_id>/"
  },
  "products": [
    {
      "productName": "Product 1",
      "url": "https://www.skroutz.gr/s/xxxxxxxx/product_1_url.html",
      "targetPrice": "115",
      "last_successful_check": ""
    },
    {
      "productName": "Product 2",
      "url": "https://www.skroutz.gr/s/xxxxxxxx/product_2_url.html",
      "targetPrice": "30",
      "last_successful_check": ""
    },
    {
      "productName": "Product 3",
      "url": "https://www.skroutz.gr/s/xxxxxxxx/product_3_url.html",
      "targetPrice": "1100",
      "last_successful_check": ""
    }
  ]
}
```

*   **`products`** (Items to monitor):
    *   `productName`: Friendly name for your notifications.
    *   `url`: The Skroutz product page URL.
    *   `targetPrice`: The price threshold for alerts.
    *   `last_successful_check`: Leave blank. Used internally to track stale entries.

*   **`notification.telegram`**: Your Telegram Webhook Apprise URL (`tgram://<bot_token>/<chat_id>/`).
    *   **Bot Token:** Follow the [Telegram Bot Guide](https://core.telegram.org/bots#how-do-i-create-a-bot) to generate one.
    *   **Chat ID:** Follow [this guide](https://www.alphr.com/find-chat-id-telegram/) to find yours.

## 💻 Usage

There are two ways to execute the script: automatically via the scheduled cron job, or manually for testing.

### Automated Run
If you ran `install.sh`, the script runs hourly in the background via cron. It includes a random 0-60s startup delay to avoid precise bot patterns and sends notifications when thresholds are met.

### Manual Run / Debug Mode
If you want to manually test your configurations and scrape immediately you can execute the script using the `--debug` flag, which shows verbose output and skips the startup delay.

```bash
source venv/bin/activate
python skroutz_price_alert.py --debug
```

> [!TIP]
> For best results, this script should **not** run behind a VPN, and should ideally be executed from a **Greek IP address**.
> * High traffic from known VPN providers will trigger strict anti-bot captchas or blocks.
> * Running from outside the Greek IP address space often results in much stricter anti-bot measures.

## ⚖️ Rate Limiting

The default configuration of this script is intentionally designed to minimize the load on Skroutz's servers and protect its users.
*   Products are checked sequentially, not concurrently.
*   A base delay, combined with randomized jitter, is enforced between each request.
*   The default installation schedules the script to run once an hour. This is more than frequent enough to catch price drops while remaining respectful.

**Good Practices:**
*   Remove items from your `config.json` once you purchase them.
*   Delete entries if you lose interest in a product or if it drops below your target price (and you act on it). Tracking unnecessary products wastes bandwidth.

These measures are important to protect users from IP bans and prevent server overloading. Please do not decrease the delays or run the cron job more frequently.

## 🗺️ Future Updates (Roadmap)

- [ ] **Cross-Platform Support:** Add install scripts for macOS and Windows.
- [ ] **More Notification Services:** Add Discord, Email, Slack, etc.
- [ ] **Enhanced Evasion:** Rotate TLS sessions and fingerprints between requests.
- [ ] **User Interface:** Add a more friendly User Interface for setup.

## 🤝 Contributing & Issues

If you have a suggestion that would make this project better, please fork the repo and create a pull request.

If you discover any bugs or issues, please open an issue in the repository. Provide as much detail as possible to help reproduce and fix the problem.

Don't forget to give the project a star! Thanks again!

## ⚠️ Disclaimer

Please use this script responsibly. This script is intended for personal, educational use. Users are solely responsible for how they use the script and must comply with Skroutz's Terms of Service. The author is not responsible for any bans, blocks, or legal issues that may arise from using this software.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
