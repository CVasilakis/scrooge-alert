# Skroutz Price Alert

![Python Version](https://img.shields.io/badge/python-3.x-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

> [!IMPORTANT]
> Skroutz is a registered trademark of Skroutz S.A. This project is an independent, unofficial tool and is not affiliated with, authorized, maintained, sponsored, or endorsed by Skroutz S.A. in any way.

Automatically track product prices on [Skroutz.gr](https://www.skroutz.gr) and get notified via Telegram (or other services supported by [Apprise](https://github.com/caronc/apprise)) when a product drops below your target price.

![Screenshot of Notification](docs/screenshot_placeholder.png) <!-- Replace docs/screenshot_placeholder.png with an actual screenshot of your notification -->

## Features

*   **Automated Tracking:** Periodically checks product prices using a configurable cron job.
*   **Custom Target Prices:** Set a specific target price for each product.
*   **Notification System:** Uses [Apprise](https://github.com/caronc/apprise) to push notifications. Alerts you on price drops, stale script entries (if a product hasn't updated in 24 hours), or script errors.
*   **Anti-Bot Evasion:** Utilizes [tls-client](https://github.com/FlorianREGAZ/Python-Tls-Client) with impersonation headers and randomized delays/jitter to bypass basic anti-bot protections.
*   **Concurrency Safe:** Uses [filelock](https://github.com/tox-dev/filelock) to ensure only one instance of the script runs at a time.

## Prerequisites

*   Linux/Unix environment.
*   Python 3 installed.
*   crontab available for scheduling.

## Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/CVasilakis/skroutz-price-alert
    cd skroutz-price-alert
    ```

2.  **Run the installation script:**
    The `install.sh` script will automatically create a Python virtual environment (`venv`), install the required dependencies (from `requirements.txt`), and set up a cron job to run the script hourly. It is safe to run this script multiple times—it will cleanly update the virtual environment, refresh dependencies, and update the cron job without duplicating entries.
    ```bash
    chmod +x install.sh
    ./install.sh
    ```

## Configuration

Before running the script, you need to configure the products to monitor and notification settings in `config.json`.

```json
{
  "notification": {
    "telegram": "tgram://<bot_token>/<chat_id>/"
  },
  "products": [
    {
      "productName": "Samsung SSD 2TB",
      "url": "https://www.skroutz.gr/s/39358691/Samsung-990-PRO-SSD-2TB-M-2-NVMe-PCI-Express-4-0-MZ-V9P2T0BW.html",
      "targetPrice": "115",
      "last_successful_check": ""
    }
  ]
}
```

*   **notification.telegram**: Your Apprise-formatted Telegram URL.

    **Telegram Setup Guide:**
    Setting up Telegram is free and takes about 15-20 minutes max. Here's what you need to do:
    *   Create a bot by following the official [Telegram bot guide](https://core.telegram.org/bots#how-do-i-create-a-bot). After setup, you'll get a bot token like this: `1825365092:HDSH6d7h65SDJd762vvsh-Tdfsd835C`.
    *   Find the chat ID where you want to receive messages. [This guide](https://www.alphr.com/find-chat-id-telegram/) shows how to locate it—it will look something like: `1927562839`.
    
    Once you have both, construct your URL in this format: `tgram://<bot_token>/<chat_id>/` and add it to your `config.json`. You'll start receiving notifications directly in your Telegram chats.
*   **products**: A list of items to track.
    *   `productName`: A friendly name used for the notification. Use whatever you like.
    *   `url`: The full Skroutz product URL. Just paste it here from your browser.
    *   `targetPrice`: The price threshold below which you want to be notified.
    *   `last_successful_check`: Used internally by the script to track stale entries. You can leave it blank initially.

## Usage

### Automated Run
If you ran `install.sh`, the script is automatically scheduled to run every hour (`0 * * * *`) via cron. It will silently update timestamps in `config.json` and send notifications when necessary. Note that in standard mode, the script includes a random startup delay (up to 60 seconds) to avoid precise periodic patterns.

### Manual Run / Debug Mode
You can manually run the script to test your configuration or scrape immediately. Use the `--debug` flag to see verbose output and skip the random startup delay.

```bash
source venv/bin/activate
python skroutz_price_alert.py --debug
```

## Rate Limiting & Disclaimer

**Responsible Usage:** The default configuration of this script is intentionally designed to minimize the load on Skroutz's servers. 
*   **Sequential Queries:** Products are checked sequentially, not concurrently.
*   **Enforced Delays:** A deliberate base delay, combined with randomized jitter, is enforced between each request.
*   **1-Hour Cron Job:** The default installation schedules the script to run once an hour (`0 * * * *`). This is more than frequent enough to catch price drops while remaining respectful.

These measures are crucial to protect users from IP bans and prevent server overloading. Please do not decrease the delays or run the cron job more frequently. 

**Disclaimer:** Please use this script responsibly. This tool is intended for personal, educational use. Users are solely responsible for how they use the tool and must comply with Skroutz's Terms of Service. The author is not responsible for any bans, blocks, or legal issues that may arise from using this software.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
