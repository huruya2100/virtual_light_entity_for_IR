import unittest.mock
from unittest.mock import patch, MagicMock
from virtual_light_entity_for_IR.main import Config, Light, HomeAssistantClient

CONFIG_PATH = "settings.json"


def test_config_get_nonexistent_key():
    with patch("builtins.open", unittest.mock.mock_open(read_data="{}")):
        config = Config(CONFIG_PATH)
        assert config.get("nonexistent.key") is None
        assert config.get("nonexistent.key", "default") == "default"


def test_config_load_invalid_json():
    with patch(
        "builtins.open", unittest.mock.mock_open(read_data="invalid json")
    ), patch("logging.error") as mock_log:
        config = Config(CONFIG_PATH)
        assert config.config == {}
        mock_log.assert_called_once()


def test_light_convert_brightness_out_of_range():
    config = MagicMock()
    config.get.return_value = {
        "1": {"min": 0, "max": 10},
        "3": {"min": 10, "max": 50},
        "5": {"min": 50, "max": 100},
    }

    light = Light(config)

    # 範囲外の上限値
    assert light.convert_brightness_to_level(150) == 5

    # 範囲内の値
    assert light.convert_brightness_to_level(30) == 3

    # 丁度境界値
    assert light.convert_brightness_to_level(10) == 3
    assert light.convert_brightness_to_level(50) == 5


def test_home_assistant_client_call_script_service_error():
    ha_client = HomeAssistantClient("http://localhost:8123", "token123")

    with patch("requests.post") as mock_post, patch("time.sleep"):
        mock_post.side_effect = Exception("Connection error")

        status, text = ha_client.call_script_service("script.test")

        assert status == 0
        assert "Connection error" in text


def test_light_change_state_with_api_error():
    config = MagicMock()
    light = Light(config)
    light.state = "OFF"

    with patch.object(
        light.home_assistant, "call_script_service"
    ) as mock_call, patch.object(light.mqtt, "connect"), patch.object(
        light.mqtt, "publish"
    ), patch.object(
        light.mqtt, "disconnect"
    ), patch(
        "logging.error"
    ) as mock_log:
        mock_call.return_value = (500, "Internal Server Error")

        light.change_virtual_state_state("ON")

        mock_call.assert_called_once()
        light.mqtt.publish.assert_called_once()
        assert light.state == "ON"  # 状態は変更されるが、APIエラーはログに記録される
