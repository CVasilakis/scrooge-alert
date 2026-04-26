from src.scraper.skroutz_price_alert import SkroutzScraper

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

def test_scrape_product_not_found(mocker):
    scraper = SkroutzScraper(silent=True)
    
    mock_session = mocker.patch("src.scraper.skroutz_price_alert.tls_client.Session")
    mock_response = mocker.Mock()
    mock_response.status_code = 404 # Simulate product page deleted
    mock_session.return_value.get.return_value = mock_response

    price = scraper.scrape_product("https://www.skroutz.gr/s/123/deleted", "Deleted Item")
    
    assert price is None
