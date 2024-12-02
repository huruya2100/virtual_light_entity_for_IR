import pytest
import unittest.mock
from unittest.mock import patch, MagicMock
from virtual_light_entity_for_IR.main import Config, MQTTClient, Light, HomeAssistantClient
CONFIG_PATH = "settings.json"

@pytest.fixture
def config():
    with patch("builtins.open", unittest.mock.mock_open(read_data='{"mqtt": {"username": "user", "password": "pass", "host": "localhost", "port": 1883, "topics": {"brightness_topic": "brightness", "light_topic": "light"}}}')):
        return Config(CONFIG_PATH)

@pytest.fixture
def mqtt_client(config):
    return MQTTClient(config)

def test_config_load(config):
    assert config.get("mqtt.username") == "user"
    assert config.get("mqtt.password") == "pass"
    assert config.get("mqtt.host") == "localhost"
    assert config.get("mqtt.port") == 1883

def test_mqtt_client_init(mqtt_client):
    assert mqtt_client.username == "user"
    assert mqtt_client.password == "pass"
    assert mqtt_client.host == "localhost"
    assert mqtt_client.port == 1883
    assert mqtt_client.brightness_topic == "brightness"
    assert mqtt_client.light_topic == "light"

def test_mqtt_client_on_connect(mqtt_client):
    client = MagicMock()
    mqtt_client.on_connect(client, None, None, 0)
    client.subscribe.assert_any_call("brightness")
    client.subscribe.assert_any_call("light/state")
    client.subscribe.assert_any_call("light/brightness")

def test_mqtt_client_on_message_brightness(mqtt_client):
    msg = MagicMock()
    msg.topic = "brightness"
    msg.payload.decode.return_value = "50.5"
    with patch.object(mqtt_client.light, 'convert_brightness_to_level', return_value=5) as mock_convert, \
         patch.object(mqtt_client.light, 'real2virtual_brightness') as mock_real2virtual:
        mqtt_client.on_message(None, None, msg)
        mock_convert.assert_called_once_with(50.5)
        mock_real2virtual.assert_called_once_with(5)

def test_mqtt_client_on_message_light_state(mqtt_client):
    msg = MagicMock()
    msg.topic = "light/state"
    msg.payload.decode.return_value = "ON"
    with patch.object(mqtt_client, 'handle_light_command') as mock_handle:
        mqtt_client.on_message(None, None, msg)
        mock_handle.assert_called_once_with("ON")

def test_mqtt_client_on_message_light_brightness(mqtt_client):
    msg = MagicMock()
    msg.topic = "light/brightness"
    msg.payload.decode.return_value = "5"
    with patch.object(mqtt_client.light, 'virtual2real_brightness') as mock_virtual2real:
        mqtt_client.on_message(None, None, msg)
        mock_virtual2real.assert_called_once_with(5)

def test_light_turn_on():
    config = MagicMock()
    light = Light(config)
    with patch.object(light.home_assistant, 'call_ir_service', return_value=(200, "OK")) as mock_call:
        light.turn_on("device")
        mock_call.assert_called_once_with("device", "on_service", 1)
        assert light.state == "on"

def test_light_turn_off():
    config = MagicMock()
    light = Light(config)
    with patch.object(light.home_assistant, 'call_ir_service', return_value=(200, "OK")) as mock_call:
        light.turn_off("device")
        mock_call.assert_called_once_with("device", "off_service", 1)
        assert light.state == "off"
