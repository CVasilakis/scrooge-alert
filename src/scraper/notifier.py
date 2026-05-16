import apprise
from config import APPRISE_PLACEHOLDERS

class Notifier:
    def __init__(self, notification_urls: str):
        self.app_notif = apprise.Apprise()
        self.has_services = False
        if notification_urls:
            for url in notification_urls.split(','):
                url = url.strip()
                if url and not any(p in url for p in APPRISE_PLACEHOLDERS):
                    if self.app_notif.add(url):
                        self.has_services = True

    def notify(self, title: str, body: str) -> bool:
        """Sends a notification with the given title and body."""
        return bool(self.app_notif.notify(title=title, body=body))

    def notify_low_price(self, product_name: str, target_price: float, current_price: float, url: str, currency: str = '€') -> bool:
        return self.notify(
            title='Skroutz Price Drop Alert!',
            body=f'{product_name} is now available for {current_price}{currency}, which is below your target of {target_price}{currency}.\nView it here: {url}'
        )

    def notify_old_entries(self, product_name: str, hours: int, url: str) -> bool:
        return self.notify(
            title='Skroutz Tracking Stale',
            body=f'The scraping for "{product_name}" hasn\'t been successfully completed in over {hours} hours. Please check the error logs or verify if the URL is still valid.\nProduct URL: {url}'
        )

    def notify_errors(self) -> bool:
        return self.notify(
            title='Skroutz Scraping Errors',
            body='The Skroutz Price Alert script encountered errors while checking some of your products. Please review the error logs for more details.'
        )

    def notify_crash(self) -> bool:
        return self.notify(
            title='Skroutz Script Crash',
            body='The Skroutz Price Alert script failed unexpectedly. Please review the error logs for more details on the crash.'
        )

    def notify_test(self) -> list:
        title = 'Skroutz Test Notification'
        body = 'This is a test message to confirm that your Skroutz Price Alert notifications are configured correctly!'

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
