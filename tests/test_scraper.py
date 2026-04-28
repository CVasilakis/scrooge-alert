import pytest
import signal
from src.scraper.skroutz_price_alert import SkroutzScraper, ProductsManager

def test_scrape_product_success(mocker):
    scraper = SkroutzScraper(silent=True)

    # Mock the network session
    mock_session = mocker.patch("src.scraper.skroutz_price_alert.tls_client.Session")
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"price_min": 149.99}
    mock_session.return_value.get.return_value = mock_response

    price = scraper.scrape_product("https://www.skroutz.gr/s/123/test", "Test Item")

    assert price == 149.99
    assert isinstance(price, float)

def test_scrape_product_not_found(mocker):
    scraper = SkroutzScraper(silent=False) # Test silent=False path

    mock_session = mocker.patch("src.scraper.skroutz_price_alert.tls_client.Session")
    mock_response = mocker.Mock()
    mock_response.status_code = 404 # Simulate product page deleted
    mock_session.return_value.get.return_value = mock_response

    price = scraper.scrape_product("https://www.skroutz.gr/s/123/deleted", "Deleted Item")

    assert price is None

def test_signal_handler():
    scraper = SkroutzScraper(silent=False)
    scraper.signal_handler(signal.SIGINT, None)
    assert scraper.interrupted

    scraper = SkroutzScraper(silent=False)
    scraper.signal_handler(signal.SIGTERM, None)
    assert scraper.interrupted

def test_sleep_with_jitter(mocker):
    scraper = SkroutzScraper(silent=False)
    mocker.patch("src.scraper.skroutz_price_alert.time.sleep")
    mock_time = mocker.patch("src.scraper.skroutz_price_alert.time.time")

    # Simulate time advancing to exit loop immediately
    mock_time.side_effect = [0, 10, 10, 10, 10]

    scraper._sleep_with_jitter(0.1)

    # Test interruption during sleep
    scraper.interrupted = True
    mock_time.side_effect = [0, 0, 0, 0, 0] # Need enough to start loop
    scraper._sleep_with_jitter(10)
    # Loop should exit quickly

def test_scrape_product_invalid_url():
    scraper = SkroutzScraper(silent=False)
    assert scraper.scrape_product("https://www.skroutz.gr/c/123/test", "Test") is None

def test_scrape_product_rate_limit(mocker):
    scraper = SkroutzScraper(silent=True)
    mock_session = mocker.patch("src.scraper.skroutz_price_alert.tls_client.Session")
    mock_response = mocker.Mock()
    mock_response.status_code = 403
    mock_session.return_value.get.return_value = mock_response

    with pytest.raises(Exception, match="Blocked or rate limited"):
        scraper.scrape_product("https://www.skroutz.gr/s/123/test", "Test")

def test_scrape_product_http_error(mocker):
    scraper = SkroutzScraper(silent=True)
    mock_session = mocker.patch("src.scraper.skroutz_price_alert.tls_client.Session")
    mock_response = mocker.Mock()
    mock_response.status_code = 500
    mock_session.return_value.get.return_value = mock_response

    with pytest.raises(Exception, match="HTTP request failed with status code 500"):
        scraper.scrape_product("https://www.skroutz.gr/s/123/test", "Test")

def test_scrape_product_no_price(mocker):
    scraper = SkroutzScraper(silent=False)
    mock_session = mocker.patch("src.scraper.skroutz_price_alert.tls_client.Session")
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"price_min": None}
    mock_session.return_value.get.return_value = mock_response

    assert scraper.scrape_product("https://www.skroutz.gr/s/123/test", "Test") is None

def test_scrape_product_price_format(mocker):
    scraper = SkroutzScraper(silent=True)
    mock_session = mocker.patch("src.scraper.skroutz_price_alert.tls_client.Session")
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"price_min": "1.234,56"}
    mock_session.return_value.get.return_value = mock_response

    assert scraper.scrape_product("https://www.skroutz.gr/s/123/test", "Test") == 1234.56

def test_process_products(mocker):
    scraper = SkroutzScraper(silent=False)
    manager = mocker.Mock(spec=ProductsManager)
    manager.products_data = {
        "products": [
            {"skip": True, "productName": "Skipped"},
            {"url": "", "productName": "No URL"},
            {"url": "https://ro.domain.ro/s/123/test", "productName": "Target Missing"},
            {"url": "https://www.skroutz.gr/s/123/test1", "targetPrice": 200, "productName": "Notify"},
            {"url": "https://www.skroutz.gr/s/123/test2", "targetPrice": 50, "productName": "No Notify"},
            {"url": "https://www.skroutz.gr/s/123/test3", "targetPrice": 50, "productName": "Error JSON"},
            {"url": "https://www.skroutz.gr/s/123/test4", "targetPrice": 50, "productName": "Error Exception"}
        ]
    }
    notifier = mocker.Mock()
    notifier.has_services = True

    # We patch _sleep_with_jitter to avoid waiting
    mocker.patch.object(scraper, '_sleep_with_jitter')

    # We patch scrape_product to return different things for different URLs
    import json
    def mock_scrape(url, name):
        if "test1" in url:
            return 100.0
        elif "test2" in url:
            return 100.0
        elif "test3" in url:
            raise json.JSONDecodeError("msg", "doc", 0)
        elif "test4" in url:
            raise Exception("general error")
        return 100.0

    mocker.patch.object(scraper, 'scrape_product', side_effect=mock_scrape)
    mocker.patch("src.scraper.skroutz_price_alert.ErrorHandler.save_traceback")

    scraper.process_products(manager, notifier, "data_dir")

    assert manager.update_product.call_count == 3
    notifier.notify_low_price.assert_called()
    notifier.notify_errors.assert_called_once()
    manager.save_atomically.assert_called_once()
    manager.check_for_old_entries.assert_called_once()

def test_process_products_interrupted(mocker):
    scraper = SkroutzScraper(silent=False)
    scraper.interrupted = True # Immediately interrupted
    manager = mocker.Mock(spec=ProductsManager)
    manager.products_data = {"products": [{"url": "https://www.skroutz.gr/s/123/test"}]}
    notifier = mocker.Mock()

    mocker.patch.object(scraper, '_sleep_with_jitter')

    scraper.process_products(manager, notifier, "data_dir")

    manager.save_atomically.assert_called_once()
    manager.check_for_old_entries.assert_not_called()

def test_process_products_interrupt_during_loop(mocker):
    scraper = SkroutzScraper(silent=False)
    manager = mocker.Mock(spec=ProductsManager)
    manager.products_data = {
        "products": [
            {"url": "https://www.skroutz.gr/s/123/test"},
        ]
    }
    notifier = mocker.Mock()

    def mock_sleep(*args, **kwargs):
        scraper.interrupted = True

    mocker.patch.object(scraper, '_sleep_with_jitter', side_effect=mock_sleep)

    scraper.process_products(manager, notifier, "data_dir")

    manager.save_atomically.assert_called_once()

def test_process_products_interrupt_during_retry(mocker):
    scraper = SkroutzScraper(silent=True)
    manager = mocker.Mock(spec=ProductsManager)
    manager.products_data = {
        "products": [
            {"url": "https://www.skroutz.gr/s/123/test"},
        ]
    }
    notifier = mocker.Mock()

    mocker.patch.object(scraper, '_sleep_with_jitter')

    def mock_scrape(*args, **kwargs):
        scraper.interrupted = True
        return None

    mocker.patch.object(scraper, 'scrape_product', side_effect=mock_scrape)

    scraper.process_products(manager, notifier, "data_dir")
    manager.save_atomically.assert_called_once()

def test_process_products_no_price(mocker):
    scraper = SkroutzScraper(silent=True)
    manager = mocker.Mock(spec=ProductsManager)
    manager.products_data = {
        "products": [
            {"url": "https://www.skroutz.gr/s/123/test"},
        ]
    }
    notifier = mocker.Mock()

    mocker.patch.object(scraper, '_sleep_with_jitter')
    mocker.patch.object(scraper, 'scrape_product', return_value=None)

    scraper.process_products(manager, notifier, "data_dir")
    # should not call update_product since price is None
    manager.update_product.assert_not_called()

def test_sleep_with_jitter_not_silent(mocker, capsys):
    scraper = SkroutzScraper(silent=False)
    mocker.patch("src.scraper.skroutz_price_alert.time.sleep")
    mock_time = mocker.patch("src.scraper.skroutz_price_alert.time.time")
    # Time advances such that we do one print loop then exit
    mock_time.side_effect = [0, 0, 0, 10, 10, 10, 10, 10]

    scraper._sleep_with_jitter(1.0)
    out, _ = capsys.readouterr()
    assert "Sleeping for" in out

def test_process_products_invalid_target_price(mocker, capsys):
    scraper = SkroutzScraper(silent=False)
    manager = mocker.Mock(spec=ProductsManager)
    manager.products_data = {
        "products": [
            {"url": "https://www.skroutz.gr/s/123/test", "targetPrice": "invalid_format", "productName": "Bad Price Product"},
            {"url": "https://www.skroutz.gr/s/123/test2", "targetPrice": ["list?"], "productName": "List Price Product"},
        ]
    }
    notifier = mocker.Mock()

    mocker.patch.object(scraper, '_sleep_with_jitter')
    mock_scrape = mocker.patch.object(scraper, 'scrape_product')

    scraper.process_products(manager, notifier, "data_dir")

    out, _ = capsys.readouterr()
    assert "Invalid target price 'invalid_format', skipping product." in out
    assert "Invalid target price '['list?']', skipping product." in out
    mock_scrape.assert_not_called()

def test_process_products_no_notification_services(mocker, capsys):
    scraper = SkroutzScraper(silent=False)
    manager = mocker.Mock(spec=ProductsManager)
    manager.products_data = {
        "products": [
            {"url": "https://www.skroutz.gr/s/123/test_no_notify", "targetPrice": 200, "productName": "No Notify Service"},
            {"url": "https://www.skroutz.gr/s/123/test_interrupt_retry", "targetPrice": 200, "productName": "Interrupt in retry"}
        ]
    }
    notifier = mocker.Mock()
    notifier.has_services = False

    # Setup mock_scrape
    def mock_scrape(url, name):
        if "test_no_notify" in url:
            return 100.0 # Below target price, triggers 🚨 but no service
        elif "test_interrupt_retry" in url:
            scraper.interrupted = True
            raise Exception("Force retry")
        return 100.0

    mocker.patch.object(scraper, 'scrape_product', side_effect=mock_scrape)

    # We patch _sleep_with_jitter so it doesn't actually sleep
    mocker.patch.object(scraper, '_sleep_with_jitter')

    scraper.process_products(manager, notifier, "data_dir")

    out, _ = capsys.readouterr()
    assert "No notification sent (no services configured in .env)" in out
