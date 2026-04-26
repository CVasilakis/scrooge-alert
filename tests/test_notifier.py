from src.scraper.skroutz_price_alert import Notifier

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
