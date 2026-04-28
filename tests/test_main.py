import pytest
from src.scraper.skroutz_price_alert import main

@pytest.fixture
def mock_env(mocker):
    mocker.patch("src.scraper.skroutz_price_alert.os.environ.get", return_value="telegram://token")
    mocker.patch("src.scraper.skroutz_price_alert.load_dotenv", return_value=True)

def test_main_no_products_file(mocker, mock_env):
    mocker.patch("sys.argv", ["skroutz_price_alert.py", "--silent"])
    mocker.patch("src.scraper.skroutz_price_alert.os.path.exists", return_value=False)
    mocker.patch("src.scraper.skroutz_price_alert.os.makedirs")

    main() # Should return early

def test_main_no_products_file_loud(mocker, mock_env):
    mocker.patch("sys.argv", ["skroutz_price_alert.py"])
    mocker.patch("src.scraper.skroutz_price_alert.os.path.exists", return_value=False)
    mocker.patch("src.scraper.skroutz_price_alert.os.makedirs")

    main() # Should return early and print

def test_main_test_notification(mocker, mock_env):
    mocker.patch("sys.argv", ["skroutz_price_alert.py", "--test-notification"])
    # mock exists to bypass the products file check
    mocker.patch("src.scraper.skroutz_price_alert.os.path.exists", return_value=True)
    mock_notifier = mocker.patch("src.scraper.skroutz_price_alert.Notifier")

    main()
    mock_notifier.return_value.notify.assert_called_once()

def test_main_test_notification_silent(mocker, mock_env):
    mocker.patch("sys.argv", ["skroutz_price_alert.py", "--test-notification", "--silent"])
    mocker.patch("src.scraper.skroutz_price_alert.os.path.exists", return_value=True)
    mock_notifier = mocker.patch("src.scraper.skroutz_price_alert.Notifier")

    main()
    mock_notifier.return_value.notify.assert_called_once()

def test_main_normal_execution(mocker, mock_env):
    mocker.patch("sys.argv", ["skroutz_price_alert.py"])
    mocker.patch("src.scraper.skroutz_price_alert.os.path.exists", return_value=True)

    mock_manager = mocker.patch("src.scraper.skroutz_price_alert.ProductsManager")
    mock_manager.return_value.load.return_value = {"products": [{"url": "http://test"}]}

    mock_scraper = mocker.patch("src.scraper.skroutz_price_alert.SkroutzScraper")

    # Use dummy lock
    mocker.patch("src.scraper.skroutz_price_alert.FileLock")

    main()
    mock_scraper.return_value.process_products.assert_called_once()

def test_main_normal_execution_with_placeholders(mocker):
    mocker.patch("sys.argv", ["skroutz_price_alert.py"])
    mocker.patch("src.scraper.skroutz_price_alert.os.environ.get", return_value="telegram://<token>")
    mocker.patch("src.scraper.skroutz_price_alert.load_dotenv", return_value=True)

    def mock_exists(path):
        # We need products.json and .env to exist to trigger all print lines
        return True

    mocker.patch("src.scraper.skroutz_price_alert.os.path.exists", side_effect=mock_exists)

    mock_manager = mocker.patch("src.scraper.skroutz_price_alert.ProductsManager")
    mock_manager.return_value.load.return_value = {"products": []}

    mocker.patch("src.scraper.skroutz_price_alert.FileLock")
    mocker.patch("src.scraper.skroutz_price_alert.SkroutzScraper")

    main()

def test_main_lock_timeout(mocker, mock_env):
    mocker.patch("sys.argv", ["skroutz_price_alert.py"])
    mocker.patch("src.scraper.skroutz_price_alert.os.path.exists", return_value=True)
    mocker.patch("src.scraper.skroutz_price_alert.ProductsManager")

    from src.scraper.skroutz_price_alert import Timeout

    class MockLock:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): raise Timeout("lock_file")
        def __exit__(self, *args): pass

    mocker.patch("src.scraper.skroutz_price_alert.FileLock", MockLock)

    main() # should handle Timeout gracefully

def test_main_lock_timeout_silent(mocker, mock_env):
    mocker.patch("sys.argv", ["skroutz_price_alert.py", "--silent"])
    mocker.patch("src.scraper.skroutz_price_alert.os.path.exists", return_value=True)
    mocker.patch("src.scraper.skroutz_price_alert.ProductsManager")

    from src.scraper.skroutz_price_alert import Timeout

    class MockLock:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): raise Timeout("lock_file")
        def __exit__(self, *args): pass

    mocker.patch("src.scraper.skroutz_price_alert.FileLock", MockLock)
    main()

def test_main_exception(mocker, mock_env):
    mocker.patch("sys.argv", ["skroutz_price_alert.py"])
    mocker.patch("src.scraper.skroutz_price_alert.os.path.exists", return_value=True)
    mocker.patch("src.scraper.skroutz_price_alert.ProductsManager")
    mocker.patch("src.scraper.skroutz_price_alert.apprise.Apprise")

    mock_notify = mocker.patch("src.scraper.skroutz_price_alert.Notifier.notify")
    mock_error_handler = mocker.patch("src.scraper.skroutz_price_alert.ErrorHandler")

    class MockLock:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): raise RuntimeError("Unexpected error")
        def __exit__(self, *args): pass

    mocker.patch("src.scraper.skroutz_price_alert.FileLock", MockLock)

    main()
    mock_error_handler.save_traceback.assert_called_once()
    mock_notify.assert_called_once()

def test_main_no_env(mocker):
    mocker.patch("sys.argv", ["skroutz_price_alert.py"])
    mocker.patch("src.scraper.skroutz_price_alert.os.environ.get", return_value="")
    mocker.patch("src.scraper.skroutz_price_alert.load_dotenv", return_value=False)
    mocker.patch("src.scraper.skroutz_price_alert.os.path.exists", return_value=True)
    mocker.patch("src.scraper.skroutz_price_alert.ProductsManager")
    mocker.patch("src.scraper.skroutz_price_alert.FileLock")
    mocker.patch("src.scraper.skroutz_price_alert.SkroutzScraper")

    main()

def test_main_block(mocker):
    mocker.patch("sys.argv", ["skroutz_price_alert.py", "--silent"])
    mocker.patch("src.scraper.skroutz_price_alert.os.path.exists", return_value=False)
    mocker.patch("src.scraper.skroutz_price_alert.os.makedirs")
    import runpy
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        runpy.run_module("src.scraper.skroutz_price_alert", run_name="__main__")
