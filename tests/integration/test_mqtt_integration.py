"""
MQTT統合テスト

実際のMQTTブローカー（mosquitto）に接続して動作を確認します。
ブローカーが localhost:1883 で起動していることが必要です。
"""
import json
import time

import pytest
from paho.mqtt import client as paho_mqtt

from virtual_light_entity_for_IR.mqtt import BaseMQTTClient, MQTTPublisher

MQTT_HOST = "localhost"
MQTT_PORT = 1883


def _make_config(host=MQTT_HOST, port=MQTT_PORT):
    """テスト用のConfigモックを作る（認証なし）"""
    from unittest.mock import MagicMock

    config = MagicMock()
    config.get.side_effect = lambda key, default=None: {
        "mqtt.host": host,
        "mqtt.port": port,
        "mqtt.username": None,
        "mqtt.password": None,
    }.get(key, default)
    return config


# --- BaseMQTTClient ---

class TestBaseMQTTClientIntegration:
    def test_connect_and_disconnect(self):
        config = _make_config()
        client = BaseMQTTClient(config)

        assert client.connect() is True
        assert client.is_connected is True

        client.disconnect()
        assert client.is_connected is False

    def test_publish_reaches_broker(self, collector):
        """publishしたメッセージが実際にブローカーを経由して届くことを確認"""
        topic = "test/base/publish"
        collector._messages.clear()

        # サブスクライブしてからパブリッシュ
        sub_client = paho_mqtt.Client(client_id="sub_base", protocol=paho_mqtt.MQTTv5)
        sub_client.on_message = collector.on_message
        sub_client.connect(MQTT_HOST, MQTT_PORT)
        sub_client.subscribe(topic)
        sub_client.loop_start()
        time.sleep(0.2)

        config = _make_config()
        pub = BaseMQTTClient(config)
        pub.connect()
        pub.publish(topic, "hello")

        msgs = collector.wait_for(topic, count=1, timeout=5)

        sub_client.loop_stop()
        sub_client.disconnect()
        pub.disconnect()

        assert msgs == ["hello"]

    def test_publish_dict_is_serialized_as_json(self, collector):
        """辞書をpublishするとJSONにシリアライズされることを確認"""
        topic = "test/base/json"
        collector._messages.clear()

        sub_client = paho_mqtt.Client(client_id="sub_json", protocol=paho_mqtt.MQTTv5)
        sub_client.on_message = collector.on_message
        sub_client.connect(MQTT_HOST, MQTT_PORT)
        sub_client.subscribe(topic)
        sub_client.loop_start()
        time.sleep(0.2)

        config = _make_config()
        pub = BaseMQTTClient(config)
        pub.connect()
        pub.publish(topic, {"state": "ON", "brightness": 3})

        msgs = collector.wait_for(topic, count=1, timeout=5)

        sub_client.loop_stop()
        sub_client.disconnect()
        pub.disconnect()

        assert len(msgs) == 1
        assert json.loads(msgs[0]) == {"state": "ON", "brightness": 3}


# --- MQTTPublisher ---

class TestMQTTPublisherIntegration:
    def test_safe_publish(self, collector):
        """safe_publishがブローカー経由でメッセージを届けることを確認"""
        topic = "test/publisher/safe"
        collector._messages.clear()

        sub_client = paho_mqtt.Client(client_id="sub_safe", protocol=paho_mqtt.MQTTv5)
        sub_client.on_message = collector.on_message
        sub_client.connect(MQTT_HOST, MQTT_PORT)
        sub_client.subscribe(topic)
        sub_client.loop_start()
        time.sleep(0.2)

        config = _make_config()
        pub = MQTTPublisher(config)
        pub.connect()
        pub.safe_publish(topic, {"state": "OFF", "brightness": 0, "light_id": "room"})

        msgs = collector.wait_for(topic, count=1, timeout=5)

        sub_client.loop_stop()
        sub_client.disconnect()
        pub.disconnect()

        assert len(msgs) == 1
        data = json.loads(msgs[0])
        assert data["state"] == "OFF"
        assert data["light_id"] == "room"

    def test_publish_light_state_on(self, collector):
        """publish_light_stateがON状態と明るさを正しく送信することを確認"""
        topic = "test/publisher/light_state"
        collector._messages.clear()

        sub_client = paho_mqtt.Client(
            client_id="sub_light_state", protocol=paho_mqtt.MQTTv5
        )
        sub_client.on_message = collector.on_message
        sub_client.connect(MQTT_HOST, MQTT_PORT)
        sub_client.subscribe(topic)
        sub_client.loop_start()
        time.sleep(0.2)

        config = _make_config()
        pub = MQTTPublisher(config)
        pub.connect()
        pub.publish_light_state(topic, "ON", brightness=4)

        msgs = collector.wait_for(topic, count=1, timeout=5)

        sub_client.loop_stop()
        sub_client.disconnect()
        pub.disconnect()

        assert len(msgs) == 1
        data = json.loads(msgs[0])
        assert data["state"] == "ON"
        assert data["brightness"] == 4

    def test_publish_light_state_off(self, collector):
        """publish_light_stateがOFF状態を正しく送信することを確認"""
        topic = "test/publisher/light_off"
        collector._messages.clear()

        sub_client = paho_mqtt.Client(
            client_id="sub_light_off", protocol=paho_mqtt.MQTTv5
        )
        sub_client.on_message = collector.on_message
        sub_client.connect(MQTT_HOST, MQTT_PORT)
        sub_client.subscribe(topic)
        sub_client.loop_start()
        time.sleep(0.2)

        config = _make_config()
        pub = MQTTPublisher(config)
        pub.connect()
        pub.publish_light_state(topic, "OFF")

        msgs = collector.wait_for(topic, count=1, timeout=5)

        sub_client.loop_stop()
        sub_client.disconnect()
        pub.disconnect()

        assert len(msgs) == 1
        data = json.loads(msgs[0])
        assert data["state"] == "OFF"
        assert "brightness" not in data

    def test_safe_publish_auto_connects(self, collector):
        """safe_publishは未接続でも自動的に接続して送信することを確認"""
        topic = "test/publisher/auto_connect"
        collector._messages.clear()

        sub_client = paho_mqtt.Client(
            client_id="sub_auto", protocol=paho_mqtt.MQTTv5
        )
        sub_client.on_message = collector.on_message
        sub_client.connect(MQTT_HOST, MQTT_PORT)
        sub_client.subscribe(topic)
        sub_client.loop_start()
        time.sleep(0.2)

        config = _make_config()
        pub = MQTTPublisher(config)
        # connect() を呼ばずに safe_publish を呼ぶ
        pub.safe_publish(topic, {"auto": True})

        msgs = collector.wait_for(topic, count=1, timeout=5)

        sub_client.loop_stop()
        sub_client.disconnect()
        pub.disconnect()

        assert len(msgs) == 1
        assert json.loads(msgs[0])["auto"] is True
