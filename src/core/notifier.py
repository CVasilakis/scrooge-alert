import apprise
from urllib.parse import urlparse
from typing import TYPE_CHECKING
from constants import APPRISE_PLACEHOLDERS

if TYPE_CHECKING:
    from models.base import BaseTrackedItem

class Notifier:
    def __init__(self, notification_urls: str):
        """Initializes the Notifier with a list of notification URLs.

        Args:
            notification_urls (str): A comma-separated list of Apprise notification URLs.
        """
        self.app_notif = apprise.Apprise()
        self.has_services = False
        if notification_urls:
            for url in notification_urls.split(','):
                url = url.strip()
                if url and not any(p in url for p in APPRISE_PLACEHOLDERS):
                    if self.app_notif.add(url):
                        self.has_services = True

    def _extract_site(self, url: str) -> str:
        """Extracts a human-readable site name from a product URL dynamically."""
        if not url:
            return "Unknown Site"
        try:
            domain = urlparse(url).netloc.lower()
            if domain.startswith('www.'):
                domain = domain[4:]
            if not domain:
                return "Unknown Site"
            # Return the main domain name capitalized (e.g. 'skroutz.gr' -> 'Skroutz')
            return domain.split('.')[0].capitalize()
        except Exception:
            return "Unknown Site"

    def notify(self, title: str, body: str) -> bool:
        """Sends a notification with the given title and body.

        Args:
            title (str): The title of the notification.
            body (str): The main content/body of the notification.

        Returns:
            bool: True if the notification was sent successfully, False otherwise.
        """
        return bool(self.app_notif.notify(title=title, body=body))

    def notify_low_price(self, product_name: str, target_price: float, current_price: float, url: str, currency: str = '€') -> bool:
        """Sends a notification about a price drop below the target price.

        Args:
            product_name (str): The name of the product.
            target_price (float): The target price set by the user.
            current_price (float): The current price of the product.
            url (str): The URL of the product.
            currency (str): The currency symbol. Defaults to '€'.

        Returns:
            bool: True if the notification was sent successfully, False otherwise.
        """
        site = self._extract_site(url)
        return self.notify(
            title='Scrooge Alert - Price Drop!',
            body=f'{product_name} is now available for {current_price}{currency} in {site}, which is below your target of {target_price}{currency}.\nView it here: {url}'
        )

    def notify_old_entries(self, product_name: str, hours: int, url: str) -> bool:
        """Sends a notification about a product that hasn't been successfully checked recently.

        Args:
            product_name (str): The name of the product.
            hours (int): The number of hours since the last successful check.
            url (str): The URL of the product.

        Returns:
            bool: True if the notification was sent successfully, False otherwise.
        """
        site = self._extract_site(url)
        return self.notify(
            title='Scrooge Alert - Tracking Stale',
            body=f'The scraping for "{product_name}" on {site} hasn\'t been successfully completed in over {hours} hours. Please check the error logs or verify if the URL is still valid.\nProduct URL: {url}'
        )

    def notify_errors(self, failed_items: list[tuple['BaseTrackedItem', Exception]]) -> bool:
        """Sends a notification indicating that specific errors occurred during scraping.

        Formats a summary of the failed products and their corresponding errors.
        If many errors occurred, the list is truncated to prevent notification bloat.

        Args:
            failed_items (list[tuple[Product, Exception]]): A list of tuples containing
                the product that failed and the exception that caused the failure.

        Returns:
            bool: True if the notification was sent successfully, False otherwise.
        """
        if not failed_items:
            return False

        # Extract site name from the first failed item to give context
        site = self._extract_site(failed_items[0][0].url)
        title = f'Scrooge Alert - Scraping Errors on {site}'

        MAX_ERRORS_TO_SHOW = 5
        body_lines = [f"The script encountered errors while checking {len(failed_items)} product(s) on {site}:\n"]

        for product, error in failed_items[:MAX_ERRORS_TO_SHOW]:
            error_type = type(error).__name__
            item_name = getattr(product, 'name', 'Unknown Item')
            body_lines.append(f"- {item_name}: {error_type}")

        if len(failed_items) > MAX_ERRORS_TO_SHOW:
            remaining = len(failed_items) - MAX_ERRORS_TO_SHOW
            body_lines.append(f"... and {remaining} more errors.")

        body_lines.append("\nPlease review the error logs for more details.")

        return self.notify(title=title, body="\n".join(body_lines))

    def notify_crash(self) -> bool:
        """Sends a notification indicating that the script crashed unexpectedly.

        Returns:
            bool: True if the notification was sent successfully, False otherwise.
        """
        return self.notify(
            title='Scrooge Alert - Script Crash',
            body='The script failed unexpectedly. Please review the error logs for more details on the crash.'
        )

    def notify_test(self) -> list:
        """Sends a test notification to all configured URLs to verify setup.

        Returns:
            list: A list of tuples containing the identifier and the success status (bool).
        """
        title = 'Scrooge Alert - Test Notification'
        body = 'This is a test message to confirm that your Scrooge Alert notifications are configured correctly!'

        results = []
        for server in self.app_notif.servers:
            identifier = server.url(privacy=True)
            schema_end = identifier.find('://')
            if schema_end != -1:
                first_slash = identifier.find('/', schema_end + 3)
                if first_slash != -1:
                    identifier = identifier[:first_slash] + '/...'

            try:
                success = server.notify(title=title, body=body)
                results.append((identifier, success))
            except Exception:
                results.append((identifier, False))
        return results
