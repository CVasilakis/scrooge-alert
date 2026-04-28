from src.scraper.skroutz_price_alert import Notifier

def test_notifier_init(mocker):
    mock_apprise = mocker.patch("src.scraper.skroutz_price_alert.apprise.Apprise")

    # Empty url
    n1 = Notifier("")
    assert not n1.has_services
    mock_apprise.return_value.add.assert_not_called()

    # URL with placeholders
    n2 = Notifier("telegram://<bot_token>")
    assert not n2.has_services
    mock_apprise.return_value.add.assert_not_called()

    # Valid url
    n3 = Notifier("telegram://bot_token")
    assert n3.has_services
    mock_apprise.return_value.add.assert_called_with("telegram://bot_token")

def test_notify(mocker):
    mock_apprise = mocker.patch("src.scraper.skroutz_price_alert.apprise.Apprise")
    notifier = Notifier("telegram://bot_token")
    notifier.notify("Test Title", "Test Body")
    mock_apprise.return_value.notify.assert_called_once_with(title="Test Title", body="Test Body")

def test_notify_low_price(mocker):
    # Mock the Apprise library so it doesn't send real alerts
    mock_apprise = mocker.patch("src.scraper.skroutz_price_alert.apprise.Apprise")

    notifier = Notifier("telegram://dummy_token")
    notifier.notify_low_price("Laptop", 1000.0, 950.0, "http://link", "€")

    # Check that apprise.notify was called with expected arguments
    mock_apprise.return_value.notify.assert_called_once()
    call_kwargs = mock_apprise.return_value.notify.call_args.kwargs
    assert "Laptop" in call_kwargs["body"]
    assert "950.0 €" in call_kwargs["body"]
    assert "Skroutz Price Drop Alert" in call_kwargs["title"]

def test_notify_old_entries(mocker):
    mock_apprise = mocker.patch("src.scraper.skroutz_price_alert.apprise.Apprise")
    notifier = Notifier("telegram://dummy_token")
    notifier.notify_old_entries(24, "http://link")
    mock_apprise.return_value.notify.assert_called_once()
    call_kwargs = mock_apprise.return_value.notify.call_args.kwargs
    assert "24 hours" in call_kwargs["body"]
    assert "http://link" in call_kwargs["body"]

def test_notify_errors(mocker):
    mock_apprise = mocker.patch("src.scraper.skroutz_price_alert.apprise.Apprise")
    notifier = Notifier("telegram://dummy_token")
    notifier.notify_errors()
    mock_apprise.return_value.notify.assert_called_once()
    call_kwargs = mock_apprise.return_value.notify.call_args.kwargs
    assert "Skroutz Scraping Errors" in call_kwargs["title"]
