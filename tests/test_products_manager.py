import json
from src.scraper.skroutz_price_alert import ProductsManager

def test_clean_url():
    manager = ProductsManager("dummy_path.json")
    url = "https://www.skroutz.gr/s/123/product.html?gclid=xyz#reviews"
    clean_url = manager._get_clean_url(url)
    assert clean_url == "https://www.skroutz.gr/s/123/product.html"

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
