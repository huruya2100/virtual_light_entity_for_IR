import pytest
import unittest.mock
from unittest.mock import patch, MagicMock
from virtual_light_entity_for_IR.config import Config
from virtual_light_entity_for_IR.light_controller import Light
from virtual_light_entity_for_IR.homeassistant import HomeAssistantClient
from virtual_light_entity_for_IR.mqtt import BaseMQTTClient, MQTTPublisher

CONFIG_PATH = "settings.json"


@pytest.fixture
def config():
    with patch(
        "builtins.open",
        unittest.mock.mock_open(
            read_data='{"mqtt": {"username": "user", "password": "pass", "host": "localhost", "port": 1883, "topics": {"brightness_topic": "brightness", "light_topic": "light"}}}'
        ),
    ):
        return Config(CONFIG_PATH)


# BaseMQTTClient クラスのテスト
def test_base_mqtt_client_setup():
    config = MagicMock()
    config.get.side_effect = lambda key, default=None: {
        "mqtt.username": "user",
        "mqtt.password": "pass",
        "mqtt.host": "localhost",
        "mqtt.port": 1883,
    }.get(key, default)

    with patch("paho.mqtt.client.Client") as mock_client:
        client_instance = MagicMock()
        mock_client.return_value = client_instance
        base_mqtt = BaseMQTTClient(config)

        assert base_mqtt.client == client_instance
        client_instance.username_pw_set.assert_called_once_with("user", "pass")


def test_base_mqtt_client_connect():
    config = MagicMock()
    config.get.side_effect = lambda key, default=None: {
        "mqtt.host": "localhost",
        "mqtt.port": 1883,
    }.get(key, default)

    with patch("paho.mqtt.client.Client") as mock_client:
        client_instance = MagicMock()
        mock_client.return_value = client_instance
        base_mqtt = BaseMQTTClient(config)

        base_mqtt.connect()
        client_instance.connect.assert_called_once_with("localhost", 1883, keepalive=60)
        client_instance.loop_start.assert_called_once()


def test_base_mqtt_client_publish():
    config = MagicMock()
    with patch("paho.mqtt.client.Client") as mock_client:
        client_instance = MagicMock()
        mock_client.return_value = client_instance

        base_mqtt = BaseMQTTClient(config)
        base_mqtt.publish("test/topic", "test message")

        client_instance.publish.assert_called_once_with("test/topic", "test message")


def test_base_mqtt_client_disconnect():
    config = MagicMock()
    with patch("paho.mqtt.client.Client") as mock_client:
        client_instance = MagicMock()
        mock_client.return_value = client_instance

        base_mqtt = BaseMQTTClient(config)
        base_mqtt.is_connected = True
        base_mqtt.disconnect()

        client_instance.disconnect.assert_called_once()


# MQTTPublisher クラスのテスト
def test_mqtt_publisher_init():
    config = MagicMock()
    with patch("paho.mqtt.client.Client"):
        publisher = MQTTPublisher(config)
        assert isinstance(publisher, BaseMQTTClient)


# HomeAssistantClient クラスのテスト
def test_home_assistant_client_call_script_service():
    ha_client = HomeAssistantClient("http://localhost:8123", "token123")

    with patch("requests.post") as mock_post, patch("time.sleep"):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"
        mock_post.return_value = mock_response

        status, text = ha_client.call_script_service("script.test", 2)

        assert status == 200
        assert text == "OK"
        assert mock_post.call_count == 2
        mock_post.assert_called_with(
            "http://localhost:8123/api/services/script/turn_on",
            headers={
                "Authorization": "Bearer token123",
                "Content-Type": "application/json",
            },
            json={"entity_id": "script.test"},
        )


# Light クラスのテスト
def test_light_set_brightness():
    config = MagicMock()
    ha_mock = MagicMock()
    mqtt_mock = MagicMock()
    light = Light("test_light", config, ha_mock, mqtt_mock)
    light.set_brightness(3)
    assert light.brightness_level == 3


def test_light_change_virtual_state_brightness_increase():
    config = MagicMock()
    ha_mock = MagicMock()
    mqtt_mock = MagicMock()
    light = Light("test_light", config, ha_mock, mqtt_mock)
    light.brightness_level = 2
    light.state = "ON"

    with patch.object(light.ir_sender, "send_command") as mock_send, patch(
        "time.sleep"
    ):
        mock_send.return_value = (200, "OK")

        light.change_virtual_state_brightness(4)

        mock_send.assert_called_once()
        mqtt_mock.safe_publish.assert_called_once()
        assert light.brightness_level == 4


def test_light_change_virtual_state_brightness_decrease():
    config = MagicMock()
    ha_mock = MagicMock()
    mqtt_mock = MagicMock()
    light = Light("test_light", config, ha_mock, mqtt_mock)
    light.brightness_level = 4
    light.state = "ON"

    with patch.object(light.ir_sender, "send_command") as mock_send, patch(
        "time.sleep"
    ):
        mock_send.return_value = (200, "OK")

        light.change_virtual_state_brightness(2)

        mock_send.assert_called_once()
        mqtt_mock.safe_publish.assert_called_once()
        assert light.brightness_level == 2


def test_light_change_virtual_state():
    config = MagicMock()
    ha_mock = MagicMock()
    mqtt_mock = MagicMock()
    light = Light("test_light", config, ha_mock, mqtt_mock)
    light.brightness_level = 3
    light.state = "OFF"

    with patch.object(light, "change_virtual_state_state") as mock_state, patch.object(
        light, "change_virtual_state_brightness"
    ) as mock_brightness:

        # 状態のみ変更の場合
        light.change_virtual_state({"state": "ON", "brightness": 3})
        mock_state.assert_called_once_with("ON")
        mock_brightness.assert_not_called()

        mock_state.reset_mock()
        mock_brightness.reset_mock()

        # 明るさのみ変更の場合
        light.state = "ON"
        light.change_virtual_state({"state": "ON", "brightness": 4})
        mock_brightness.assert_called_once_with(4)
        mock_state.assert_not_called()

        mock_state.reset_mock()
        mock_brightness.reset_mock()

        # 両方変更の場合
        light.change_virtual_state({"state": "OFF", "brightness": 1})
        mock_state.assert_called_once_with("OFF")
        assert light.pending_brightness == 1
