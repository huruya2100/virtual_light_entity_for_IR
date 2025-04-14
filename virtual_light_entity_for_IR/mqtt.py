"""
MQTTクライアント関連のモジュール
"""

import json
import logging
import time
from typing import Any, Dict, Optional, Callable, Tuple, Union

from paho.mqtt import client as mqtt_client

from .config import Config

logger = logging.getLogger(__name__)

# 再接続の設定
FIRST_RECONNECT_DELAY = 1
RECONNECT_RATE = 2
MAX_RECONNECT_DELAY = 60
MAX_RECONNECT_COUNT = 5


class BaseMQTTClient:
    """MQTTクライアントの基底クラス"""

    def __init__(self, config: Config):
        """
        コンストラクタ
        
        Args:
            config (Config): 設定オブジェクト
        """
        self.config = config
        self.client = None
        self.is_connected = False
        self.setup_client()

    def setup_client(self) -> None:
        """MQTTクライアントの初期設定"""
        self.client = mqtt_client.Client(
            client_id="",
            userdata=None,
            protocol=mqtt_client.MQTTv5,
            transport="tcp"
        )

        username = self.config.get("mqtt.username")
        password = self.config.get("mqtt.password")
        if isinstance(username, str) and isinstance(password, str):
            self.client.username_pw_set(username, password)

        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect

    def on_disconnect(self, client, userdata, rc, properties=None) -> None:
        """
        切断時のコールバック
        
        Args:
            client: MQTTクライアント
            userdata: ユーザデータ
            rc: 結果コード
            properties: プロパティ
        """
        logger.info("MQTTブローカーから切断されました")
        logger.debug(f"Client: {client}, Userdata: {userdata}, Result code: {rc}")
        self.is_connected = False
        
        # 予期せぬ切断の場合は再接続を試みる
        if rc != 0:
            logger.error("予期せぬ切断です。再接続を試みます...")
            self._reconnect()

    def _reconnect(self) -> None:
        """再接続ロジック"""
        reconnect_delay = FIRST_RECONNECT_DELAY
        reconnect_count = 0
        
        while not self.is_connected and reconnect_count < MAX_RECONNECT_COUNT:
            logger.info(f"再接続を試みます... ({reconnect_count + 1}/{MAX_RECONNECT_COUNT})")
            
            try:
                self.client.reconnect()
                self.is_connected = True
                logger.info("再接続に成功しました")
                return
            except Exception as e:
                logger.error(f"再接続に失敗しました: {e}")
                
            # 再接続の試行回数を増やす
            reconnect_count += 1
            
            # 次の再接続までの待機時間を計算（指数バックオフ）
            reconnect_delay = min(reconnect_delay * RECONNECT_RATE, MAX_RECONNECT_DELAY)
            logger.info(f"{reconnect_delay}秒後に再接続を試みます...")
            time.sleep(reconnect_delay)
        
        logger.error(f"再接続の最大試行回数({MAX_RECONNECT_COUNT})に達しました。接続を中止します。")

    def connect(self) -> bool:
        """
        MQTTブローカーに接続
        
        Returns:
            bool: 接続に成功したかどうか
        """
        if self.is_connected:
            return True

        try:
            host = self.config.get("mqtt.host")
            port = self.config.get("mqtt.port")
            
            if not host or not port:
                logger.error("MQTT設定が不足しています。ホストとポートを確認してください。")
                return False
                
            logger.info(f"MQTTブローカーに接続: {host}:{port}")
            self.client.connect(host, port, keepalive=60)
            self.client.loop_start()
            self.is_connected = True
            return True
        except Exception as e:
            logger.error(f"MQTT接続に失敗しました: {e}")
            self.is_connected = False
            return False

    def disconnect(self) -> None:
        """MQTTブローカーから切断"""
        if not self.is_connected:
            return

        try:
            logger.info("MQTTブローカーから切断します")
            self.client.loop_stop()
            self.client.disconnect()
            self.is_connected = False
        except Exception as e:
            logger.error(f"MQTT切断に失敗しました: {e}")

    def publish(self, topic: str, payload: Union[str, Dict[str, Any]]) -> None:
        """
        メッセージを発行
        
        Args:
            topic (str): トピック
            payload (Union[str, Dict]): ペイロード（文字列またはJSON変換可能な辞書）
        """
        try:
            # 辞書の場合はJSON文字列に変換
            if isinstance(payload, dict):
                payload = json.dumps(payload)
                
            logger.debug(f"メッセージを発行: {topic} {payload}")
            
            if not self.is_connected:
                self.connect()
                
            self.client.publish(topic, payload)
        except Exception as e:
            logger.error(f"メッセージ発行に失敗しました: {e}", exc_info=True)

    def subscribe(self, topic: str, qos: int = 0) -> None:
        """
        トピックを購読
        
        Args:
            topic (str): 購読するトピック
            qos (int, optional): QoSレベル。デフォルトは0
        """
        try:
            if not self.is_connected:
                self.connect()
                
            logger.debug(f"トピックを購読: {topic} (QoS: {qos})")
            self.client.subscribe(topic, qos)
        except Exception as e:
            logger.error(f"トピック購読に失敗しました: {e}", exc_info=True)

    def on_connect(self, client, userdata, flags, rc, properties=None) -> None:
        """
        接続時のコールバック
        
        Args:
            client: MQTTクライアント
            userdata: ユーザデータ
            flags: フラグ
            rc: 結果コード
            properties: プロパティ
        """
        if rc == 0:
            logger.info(f"MQTT接続完了")
            self.is_connected = True
        else:
            logger.error(f"MQTT接続失敗 結果コード: {rc}")
        
        logger.debug(
            f"Client: {client}, Userdata: {userdata}, Flags: {flags}, Properties: {properties}"
        )

    def on_message(self, client, userdata, msg) -> None:
        """
        メッセージ受信時のコールバック
        
        Args:
            client: MQTTクライアント
            userdata: ユーザデータ
            msg: 受信メッセージ
        """
        logger.info(f"メッセージ受信: {msg.topic} {msg.payload.decode('utf-8')}")
        logger.debug(f"Client: {client}, Userdata: {userdata}")


class MQTTPublisher(BaseMQTTClient):
    """発行専用MQTTクライアント"""
    
    def __init__(self, config: Config):
        """
        コンストラクタ
        
        Args:
            config (Config): 設定オブジェクト
        """
        super().__init__(config)
    
    def safe_publish(self, topic: str, payload: Dict[str, Any]) -> None:
        """
        安全にメッセージを発行（接続管理を含む）
        
        Args:
            topic (str): トピック
            payload (Dict): ペイロード
        """
        try:
            if not self.is_connected:
                self.connect()
                
            self.publish(topic, json.dumps(payload))
        except Exception as e:
            logger.error(f"安全なメッセージ発行に失敗しました: {e}", exc_info=True)
            
    def publish_light_state(self, topic: str, state: str, brightness: Optional[int] = None) -> None:
        """
        ライト状態を発行
        
        Args:
            topic (str): トピック
            state (str): ライト状態 ("ON" または "OFF")
            brightness (int, optional): 明るさレベル
        """
        payload = {"state": state}
        
        if brightness is not None:
            payload["brightness"] = brightness
            
        self.safe_publish(topic, payload)