import unittest.mock
from unittest.mock import MagicMock, patch

from virtual_light_entity_for_IR.config import Config
from virtual_light_entity_for_IR.homeassistant import HomeAssistantClient
from virtual_light_entity_for_IR.light_controller import Light

CONFIG_PATH = "settings.json"


def test_config_get_nonexistent_key():
    with patch("builtins.open", unittest.mock.mock_open(read_data="{}")):
        config = Config(CONFIG_PATH)
        assert config.get("nonexistent.key") is None
        assert config.get("nonexistent.key", "default") == "default"


def test_config_load_invalid_json(caplog):
    import logging

    with patch(
        "builtins.open", unittest.mock.mock_open(read_data="invalid json")
    ), caplog.at_level(logging.ERROR, logger="virtual_light_entity_for_IR.config"):
        config = Config(CONFIG_PATH)
        assert config.config == {}
        assert any("JSONフォーマットが無効" in r.message for r in caplog.records)


def test_light_convert_brightness_out_of_range():
    config = MagicMock()
    config.get.return_value = {
        "1": {"min": 0, "max": 10},
        "3": {"min": 10, "max": 50},
        "5": {"min": 50, "max": 100},
    }

    ha_mock = MagicMock()
    mqtt_mock = MagicMock()
    light = Light("test_light", config, ha_mock, mqtt_mock)

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
    ha_mock = MagicMock()
    mqtt_mock = MagicMock()
    light = Light("test_light", config, ha_mock, mqtt_mock)
    light.state = "OFF"

    with patch.object(light.ir_sender, "send_command") as mock_send:
        mock_send.return_value = (500, "Internal Server Error")

        light.change_virtual_state_state("ON")

        mock_send.assert_called_once()
        # APIエラーの場合、状態は変更されない
        assert light.state == "OFF"
