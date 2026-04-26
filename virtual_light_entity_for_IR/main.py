import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .config import Config
from .homeassistant import HomeAssistantClient
from .light_controller import LightController
from .mqtt import BaseMQTTClient


def _get_log_level(log_level_name: str) -> int:
    """ログレベル名をloggingのレベル値に変換する"""
    log_level = getattr(logging, log_level_name.upper(), None)
    if isinstance(log_level, int):
        return log_level
    return logging.DEBUG


# ロガー設定
logging.basicConfig(
    level=_get_log_level(os.getenv("LOG_LEVEL", "DEBUG")),
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ハンドラの設定
console_handler = logging.StreamHandler()

CONFIG_PATH = "settings.json"


class VirtualLightCore:
    """仮想ライト制御のコアクラス"""

    def __init__(self, config_path: str):
        self.config_path = config_path
        self.config = Config(config_path)
        self.event_handlers: Dict[str, List[callable]] = {}
        self.setup()

    def setup(self) -> None:
        """初期設定"""
        # Home Assistant クライアントの初期化
        ha_url = self.config.get("HomeAssistant.url")
        ha_token = self.config.get("HomeAssistant.token")
        ha_client = HomeAssistantClient(ha_url, ha_token)

        # ライトコントローラーの初期化
        self.light_controller = LightController(self.config, ha_client)

        # MQTTクライアントの初期化
        self.mqtt_client = MQTTVirtualLightClient(
            self.config, self.light_controller, self
        )

        # イベントハンドラの登録
        self.register_event_handler(
            "brightness_changed", self.light_controller.handle_brightness_change
        )
        self.register_event_handler(
            "state_changed", self.light_controller.handle_state_change
        )
        self.register_event_handler(
            "brightness_level_changed",
            self.light_controller.handle_brightness_level_change,
        )

        # 設定変更イベントを登録
        self.register_event_handler("config_changed", self.handle_config_changed)

    def register_event_handler(self, event_name: str, handler: callable) -> None:
        """イベントハンドラを登録する"""
        if event_name not in self.event_handlers:
            self.event_handlers[event_name] = []
        self.event_handlers[event_name].append(handler)

    def trigger_event(self, event_name: str, **kwargs) -> None:
        """イベントを発火する"""
        if event_name in self.event_handlers:
            for handler in self.event_handlers[event_name]:
                try:
                    handler(**kwargs)
                except Exception as e:
                    logger.error(
                        "イベントハンドラ実行中にエラーが発生しました: %s",
                        e,
                        exc_info=True,
                    )

    def handle_config_changed(self, key: str, value: Any) -> None:
        """
        設定変更イベントのハンドラ

        Args:
            key (str): 設定キー
            value (Any): 設定値
        """
        # 設定を更新
        self.config.set(key, value)
        logger.info("設定を更新しました: %s", key)

    def _publish_heartbeat(self) -> None:
        """全ライトの現在状態をハートビートトピックに送信"""
        topic = self.config.get("mqtt.heartbeat_topic")
        if not topic:
            return

        lights_state = {
            light.light_id: {
                "state": light.state,
                "brightness": light.brightness_level,
            }
            for light in self.light_controller.get_all_lights()
        }

        payload = {
            "status": "online",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "lights": lights_state,
        }

        self.mqtt_client.publish(topic, payload)
        logger.debug("ハートビートを送信しました: %s", topic)

    def run(self) -> None:
        """メインループを実行"""
        logger.info("仮想ライトエンティティを起動しています...")

        # MQTTクライアントを起動
        self.mqtt_client.connect()

        heartbeat_interval = self.config.get("mqtt.heartbeat_interval", 60)
        last_heartbeat = 0.0

        try:
            while True:
                now = time.monotonic()
                if now - last_heartbeat >= heartbeat_interval:
                    self._publish_heartbeat()
                    last_heartbeat = now
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("プログラムが中断されました")
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        """プログラムをシャットダウン"""
        logger.info("シャットダウン中...")

        # MQTTクライアントを停止
        self.mqtt_client.disconnect()


class MQTTVirtualLightClient(BaseMQTTClient):
    """仮想ライト用MQTTクライアント"""

    def __init__(
        self, config: Config, light_controller: LightController, core: VirtualLightCore
    ):
        super().__init__(config)
        self.config = config
        self.light_controller = light_controller
        self.core = core

        # ライトのトピックマッピングを作成
        self.light_topics = {}
        self.brightness_topics = {}

        for light in self.light_controller.get_all_lights():
            # ライト制御トピック
            light_topic = light.mqtt_light_topic
            if light_topic:
                self.light_topics[f"{light_topic}/set"] = light.light_id
                logger.info(
                    "ライト '%s' の制御トピックを登録: %s/set",
                    light.light_id,
                    light_topic,
                )

            # 照度トピック
            brightness_topic = light.mqtt_brightness_topic
            if brightness_topic:
                self.brightness_topics[brightness_topic] = light.light_id
                logger.info(
                    "ライト '%s' の照度トピックを登録: %s",
                    light.light_id,
                    brightness_topic,
                )

    def on_connect(self, client, userdata, flags, rc, properties=None) -> None:
        """接続時のコールバック関数"""
        super().on_connect(client, userdata, flags, rc, properties)

        # 各ライトの照度トピックを購読
        if not self.brightness_topics:
            logger.warning("照度トピックが設定されていません")
        else:
            for topic in self.brightness_topics.keys():
                logger.info("照度トピックを購読: %s", topic)
                client.subscribe(topic)

        # 各ライトの制御トピックを購読
        if not self.light_topics:
            logger.warning("ライト制御トピックが設定されていません")
        else:
            for topic in self.light_topics.keys():
                logger.info("ライト制御トピックを購読: %s", topic)
                client.subscribe(topic)

    def on_message(self, client, userdata, msg) -> None:
        """MQTTメッセージ受信時のコールバック関数"""
        super().on_message(client, userdata, msg)

        try:
            # 照度トピックのメッセージ処理
            if msg.topic in self.brightness_topics:
                self._handle_brightness_message(msg, self.brightness_topics[msg.topic])
            # ライト制御トピックのメッセージ処理
            elif msg.topic in self.light_topics:
                self._handle_light_set_message(msg, self.light_topics[msg.topic])
        except Exception as e:
            logger.error("メッセージ処理中にエラーが発生しました: %s", e, exc_info=True)

    def _handle_brightness_message(
        self, msg, specific_light_id: Optional[str] = None
    ) -> None:
        """照度センサーからのメッセージを処理"""
        try:
            payload = msg.payload.decode("utf-8")
            if specific_light_id:
                logger.info(
                    "照度データを受信: %s (ライトID: %s)", payload, specific_light_id
                )
            else:
                logger.info("照度データを受信: %s", payload)

            # 文字列から数値に変換
            try:
                lux_value = float(payload)
            except ValueError:
                logger.error("照度データを数値に変換できませんでした: %s", payload)
                return

            # ライトIDが指定されている場合はそのIDを使用
            light_id = specific_light_id

            if light_id:
                logger.info(
                    "照度データを処理: %slx (ライトID: %s)", lux_value, light_id
                )
                # 生の照度値をイベントで渡す
                self.core.trigger_event(
                    "brightness_changed", brightness=lux_value, light_id=light_id
                )
            else:
                logger.warning(
                    "照度データを受信しましたが、対象のライトIDが指定されていません"
                )

        except Exception as e:
            logger.error("照度レベルの処理に失敗しました: %s", e, exc_info=True)

    def _handle_light_set_message(self, msg, light_id: str) -> None:
        """ライト制御メッセージを処理"""
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            logger.debug(
                "ライト制御メッセージを受信: %s (ライトID: %s)", payload, light_id
            )

            # ペイロードにlight_idを追加
            payload["light_id"] = light_id

            # イベントを発火
            self.core.trigger_event("light_command", command=payload, light_id=light_id)

            has_state = "state" in payload
            has_brightness = "brightness" in payload

            if has_state:
                state = payload["state"].upper()
                self.core.trigger_event("state_changed", state=state, light_id=light_id)

            if has_brightness:
                brightness = int(payload["brightness"])
                self.core.trigger_event(
                    "brightness_level_changed",
                    brightness_level=brightness,
                    light_id=light_id,
                )

        except json.JSONDecodeError:
            logger.error(
                "不正なJSONフォーマットを受信しました: %s", msg.payload.decode("utf-8")
            )
        except Exception as e:
            logger.error("ライト制御コマンドの処理に失敗しました: %s", e, exc_info=True)


def main():
    """メインエントリーポイント"""
    try:
        core = VirtualLightCore(CONFIG_PATH)
        core.run()
    except Exception as e:
        logger.critical(
            "プログラム実行中に重大なエラーが発生しました: %s", e, exc_info=True
        )


if __name__ == "__main__":
    main()
