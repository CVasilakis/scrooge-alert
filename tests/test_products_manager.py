import json
import datetime
from src.scraper.skroutz_price_alert import ProductsManager

def test_clean_url():
    manager = ProductsManager("dummy_path.json")
    url = "https://www.skroutz.gr/s/123/product.html?gclid=xyz#reviews"
    clean_url = manager._get_clean_url(url)
    assert clean_url == "https://www.skroutz.gr/s/123/product.html"

    assert manager._get_clean_url("") == ""
    assert manager._get_clean_url(None) == ""  # type: ignore

def test_load_products_json_error(tmp_path):
    file_path = tmp_path / "products.json"
    file_path.write_text("invalid json")

    manager = ProductsManager(str(file_path))
    import pytest
    with pytest.raises(json.JSONDecodeError):
        manager.load()

def test_load_and_save_products(tmp_path):
    # Setup a temporary JSON file
    file_path = tmp_path / "products.json"
    initial_data = {"products": [{"url": "https://test.com", "targetPrice": 10}]}
    file_path.write_text(json.dumps(initial_data))

    manager = ProductsManager(str(file_path))
    data = manager.load()

    assert len(data["products"]) == 1

    # Test updating a product
    manager.update_product("https://test.com", 8.5, "01-01-2024 12:00:00")
    manager.save_atomically()

    # Reload and verify
    with open(file_path) as f:
        saved_data = json.load(f)

    assert saved_data["products"][0]["last_price"] == 8.5

def test_save_atomically_no_file(tmp_path):
    file_path = tmp_path / "does_not_exist.json"
    manager = ProductsManager(str(file_path))
    manager.products_data = {"products": [{"url": "https://test.com", "targetPrice": 10}]}

    manager.save_atomically()

    with open(file_path) as f:
        saved_data = json.load(f)
    assert saved_data["products"][0]["url"] == "https://test.com"

def test_save_atomically_json_error_explicit(tmp_path, mocker):
    file_path = tmp_path / "products.json"
    initial_data = {"products": [{"url": "https://test.com", "targetPrice": 10}]}
    file_path.write_text(json.dumps(initial_data))

    manager = ProductsManager(str(file_path))
    manager.products_data = {"products": [{"url": "https://fallback.com", "targetPrice": 20}]}

    # Mock json.load to raise JSONDecodeError explicitly
    mocker.patch("src.scraper.skroutz_price_alert.json.load", side_effect=json.JSONDecodeError("msg", "doc", 0))

    manager.save_atomically()

    with open(file_path) as f:
        saved_data = json.loads(f.read())
    assert saved_data["products"][0]["url"] == "https://fallback.com"

def test_save_atomically_json_error(tmp_path):
    file_path = tmp_path / "products.json"
    file_path.write_text("invalid json")

    manager = ProductsManager(str(file_path))
    manager.products_data = {"products": [{"url": "https://test.com", "targetPrice": 10}]}

    manager.save_atomically()

    with open(file_path) as f:
        saved_data = json.load(f)
    assert saved_data["products"][0]["url"] == "https://test.com"

def test_save_atomically_duplicate_urls(tmp_path):
    file_path = tmp_path / "products.json"
    initial_data = {
        "products": [
            {"url": "https://test.com?q=1", "targetPrice": 10},
            {"url": "https://test.com?q=2", "targetPrice": 20}
        ]
    }
    file_path.write_text(json.dumps(initial_data))

    manager = ProductsManager(str(file_path))
    manager.load()
    manager.save_atomically()

    with open(file_path) as f:
        saved_data = json.load(f)
    # The duplicate should be removed because the cleaned url is the same
    assert len(saved_data["products"]) == 1
    assert saved_data["products"][0]["url"] == "https://test.com"
    assert not saved_data["products"][0]["skip"]

def test_save_atomically_os_error(tmp_path, mocker):
    file_path = tmp_path / "products.json"
    manager = ProductsManager(str(file_path))
    mocker.patch("src.scraper.skroutz_price_alert.os.replace", side_effect=OSError("Disk full"))
    import pytest
    with pytest.raises(OSError):
        manager.save_atomically()

def test_check_for_old_entries(mocker):
    notifier = mocker.Mock()
    manager = ProductsManager("dummy_path.json")

    # Set up times
    now = datetime.datetime.now()
    old_time = now - datetime.timedelta(hours=25)
    recent_time = now - datetime.timedelta(hours=5)

    manager.products_data = {
        "products": [
            {"url": "http://skip", "skip": True, "last_successful_check": old_time.strftime("%d-%m-%Y %H:%M:%S")},
            {"url": "http://old", "productName": "Old Product", "last_successful_check": old_time.strftime("%d-%m-%Y %H:%M:%S")},
            {"url": "http://recent", "last_successful_check": recent_time.strftime("%d-%m-%Y %H:%M:%S")},
            {"url": "http://invalid-date", "last_successful_check": "invalid date"}
        ]
    }

    manager.check_for_old_entries(24, notifier)

    notifier.notify_old_entries.assert_called_once_with(24, "http://old")
