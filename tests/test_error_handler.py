import os
from src.scraper.skroutz_price_alert import ErrorHandler

def test_save_traceback(tmp_path, mocker):
    mock_print_exc = mocker.patch("src.scraper.skroutz_price_alert.traceback.print_exc")

    # Test with URL and headers
    ErrorHandler.save_traceback(str(tmp_path), url="http://test", headers={"sec-ch-ua-platform": "Windows", "accept-language": "en"})

    log_path = os.path.join(str(tmp_path), "error_log.txt")
    assert os.path.exists(log_path)
    with open(log_path, "r") as f:
        content = f.read()
    assert "URL: http://test" in content
    assert "Platform: Windows, Lang: en" in content
    mock_print_exc.assert_called_once()

    # Test without URL and headers
    mock_print_exc.reset_mock()
    ErrorHandler.save_traceback(str(tmp_path))
    with open(log_path, "r") as f:
        content = f.read()
    assert "An error occurred at" in content
    mock_print_exc.assert_called_once()

def test_save_traceback_os_error(tmp_path, mocker):
    mocker.patch("builtins.open", side_effect=OSError("Permission denied"))
    import pytest
    with pytest.raises(OSError):
        ErrorHandler.save_traceback(str(tmp_path))
