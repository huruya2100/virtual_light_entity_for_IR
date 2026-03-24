"""
統合テスト用フィクスチャ
"""
import threading
import time

import pytest
from paho.mqtt import client as paho_mqtt

MQTT_HOST = "localhost"
MQTT_PORT = 1883


class MessageCollector:
    """MQTTメッセージを収集するヘルパークラス"""

    def __init__(self):
        self._messages: dict[str, list[str]] = {}
        self._lock = threading.Lock()

    def on_message(self, client, userdata, msg):
        topic = msg.topic
        payload = msg.payload.decode("utf-8")
        with self._lock:
            self._messages.setdefault(topic, []).append(payload)

    def wait_for(self, topic: str, count: int = 1, timeout: float = 5.0) -> list[str]:
        """指定トピックにメッセージが届くまで待機して返す"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                msgs = self._messages.get(topic, [])
                if len(msgs) >= count:
                    return msgs[:count]
            time.sleep(0.05)
        return []

    def clear(self):
        with self._lock:
            self._messages.clear()


@pytest.fixture(scope="session")
def mqtt_broker():
    """MQTTブローカーへの接続情報を返す"""
    return {"host": MQTT_HOST, "port": MQTT_PORT}


@pytest.fixture
def collector(mqtt_broker):
    """テスト用サブスクライバークライアントを提供する"""
    col = MessageCollector()

    client = paho_mqtt.Client(
        client_id="test_collector",
        protocol=paho_mqtt.MQTTv5,
    )
    client.on_message = col.on_message
    client.connect(mqtt_broker["host"], mqtt_broker["port"], keepalive=10)
    client.loop_start()

    # 接続確立を待つ
    time.sleep(0.3)

    yield col

    client.loop_stop()
    client.disconnect()
