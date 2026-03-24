"""
ir_sender モジュールのテスト
"""
from unittest.mock import MagicMock, patch
from virtual_light_entity_for_IR.ir_sender import (
    HomeAssistantIRSender,
    TasmotaIRSender,
    create_ir_sender,
)


# HomeAssistantIRSender のテスト

def test_ha_sender_send_command_success():
    config = MagicMock()
    config.get.return_value = "script.light_on"
    ha_mock = MagicMock()
    ha_mock.call_script_service.return_value = (200, "OK")

    sender = HomeAssistantIRSender("test_light", "lights.test_light", config, ha_mock)
    status, text = sender.send_command("on_service", repeat=1)

    ha_mock.call_script_service.assert_called_once_with("script.light_on", 1)
    assert status == 200
    assert text == "OK"


def test_ha_sender_send_command_no_script():
    config = MagicMock()
    config.get.return_value = None
    ha_mock = MagicMock()

    sender = HomeAssistantIRSender("test_light", "lights.test_light", config, ha_mock)
    status, text = sender.send_command("on_service")

    ha_mock.call_script_service.assert_not_called()
    assert status == 0
    assert "on_service" in text


def test_ha_sender_send_command_repeat():
    config = MagicMock()
    config.get.return_value = "script.brightness_up"
    ha_mock = MagicMock()
    ha_mock.call_script_service.return_value = (200, "OK")

    sender = HomeAssistantIRSender("test_light", "lights.test_light", config, ha_mock)
    sender.send_command("brightness_up_service", repeat=3)

    ha_mock.call_script_service.assert_called_once_with("script.brightness_up", 3)


# TasmotaIRSender のテスト

def test_tasmota_sender_send_command_success():
    config = MagicMock()
    config.get.side_effect = lambda key, default=None: {
        "lights.test_light.tasmota.topic": "ir_remote",
        "lights.test_light.tasmota.ir_commands.on_service": '{"Protocol":"NEC","Bits":32,"Data":"0x1FE48B7"}',
    }.get(key, default)
    mqtt_mock = MagicMock()

    sender = TasmotaIRSender("test_light", "lights.test_light", config, mqtt_mock)
    status, text = sender.send_command("on_service", repeat=1)

    mqtt_mock.publish.assert_called_once_with(
        "cmnd/ir_remote/IRsend",
        '{"Protocol":"NEC","Bits":32,"Data":"0x1FE48B7"}',
    )
    assert status == 200
    assert text == "OK"


def test_tasmota_sender_send_command_repeat():
    config = MagicMock()
    config.get.side_effect = lambda key, default=None: {
        "lights.test_light.tasmota.topic": "ir_remote",
        "lights.test_light.tasmota.ir_commands.brightness_up_service": '{"Protocol":"NEC","Bits":32,"Data":"0xABC"}',
    }.get(key, default)
    mqtt_mock = MagicMock()

    with patch("time.sleep"):
        sender = TasmotaIRSender("test_light", "lights.test_light", config, mqtt_mock)
        status, text = sender.send_command("brightness_up_service", repeat=3)

    assert mqtt_mock.publish.call_count == 3
    assert status == 200


def test_tasmota_sender_no_topic():
    config = MagicMock()
    config.get.return_value = None
    mqtt_mock = MagicMock()

    sender = TasmotaIRSender("test_light", "lights.test_light", config, mqtt_mock)
    status, text = sender.send_command("on_service")

    mqtt_mock.publish.assert_not_called()
    assert status == 0
    assert "topic" in text.lower()


def test_tasmota_sender_no_ir_command():
    config = MagicMock()
    config.get.side_effect = lambda key, default=None: {
        "lights.test_light.tasmota.topic": "ir_remote",
    }.get(key, default)
    mqtt_mock = MagicMock()

    sender = TasmotaIRSender("test_light", "lights.test_light", config, mqtt_mock)
    status, text = sender.send_command("on_service")

    mqtt_mock.publish.assert_not_called()
    assert status == 0
    assert "on_service" in text


def test_tasmota_sender_publish_error():
    config = MagicMock()
    config.get.side_effect = lambda key, default=None: {
        "lights.test_light.tasmota.topic": "ir_remote",
        "lights.test_light.tasmota.ir_commands.on_service": '{"Protocol":"NEC"}',
    }.get(key, default)
    mqtt_mock = MagicMock()
    mqtt_mock.publish.side_effect = Exception("MQTT error")

    sender = TasmotaIRSender("test_light", "lights.test_light", config, mqtt_mock)
    status, text = sender.send_command("on_service")

    assert status == 0
    assert "MQTT error" in text


# create_ir_sender ファクトリ関数のテスト

def test_create_ir_sender_homeassistant():
    config = MagicMock()
    config.get.return_value = "homeassistant"
    ha_mock = MagicMock()
    mqtt_mock = MagicMock()

    sender = create_ir_sender("test_light", "lights.test_light", config, ha_mock, mqtt_mock)

    assert isinstance(sender, HomeAssistantIRSender)


def test_create_ir_sender_tasmota():
    config = MagicMock()
    config.get.return_value = "tasmota"
    ha_mock = MagicMock()
    mqtt_mock = MagicMock()

    sender = create_ir_sender("test_light", "lights.test_light", config, ha_mock, mqtt_mock)

    assert isinstance(sender, TasmotaIRSender)


def test_create_ir_sender_default_is_homeassistant():
    config = MagicMock()
    config.get.return_value = None  # ir_sender キーが未設定
    ha_mock = MagicMock()
    mqtt_mock = MagicMock()

    sender = create_ir_sender("test_light", "lights.test_light", config, ha_mock, mqtt_mock)

    assert isinstance(sender, HomeAssistantIRSender)
