import apprise
from constants import APPRISE_PLACEHOLDERS

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
        return self.notify(
            title='Skroutz Price Drop Alert!',
            body=f'{product_name} is now available for {current_price}{currency}, which is below your target of {target_price}{currency}.\nView it here: {url}'
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
        return self.notify(
            title='Skroutz Tracking Stale',
            body=f'The scraping for "{product_name}" hasn\'t been successfully completed in over {hours} hours. Please check the error logs or verify if the URL is still valid.\nProduct URL: {url}'
        )

    def notify_errors(self) -> bool:
        """Sends a notification indicating that errors occurred during scraping.

        Returns:
            bool: True if the notification was sent successfully, False otherwise.
        """
        return self.notify(
            title='Skroutz Scraping Errors',
            body='The Scrooge Alert script encountered errors while checking some of your products. Please review the error logs for more details.'
        )

    def notify_crash(self) -> bool:
        """Sends a notification indicating that the script crashed unexpectedly.

        Returns:
            bool: True if the notification was sent successfully, False otherwise.
        """
        return self.notify(
            title='Skroutz Script Crash',
            body='The Scrooge Alert script failed unexpectedly. Please review the error logs for more details on the crash.'
        )

    def notify_test(self) -> list:
        """Sends a test notification to all configured URLs to verify setup.

        Returns:
            list: A list of tuples containing the identifier and the success status (bool).
        """
        title = 'Skroutz Test Notification'
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
