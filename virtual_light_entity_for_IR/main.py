import threading
import logging
import time
from typing import Dict, Any, Optional, List, Union
import json
from config import Config
from mqtt import BaseMQTTClient, MQTTPublisher
from light_controller import LightController
from homeassistant import HomeAssistantClient

# ロガー設定
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s"
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
            "brightness_level_changed", self.light_controller.handle_brightness_level_change
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
                        f"イベントハンドラ実行中にエラーが発生しました: {e}",
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
        logger.info(f"設定を更新しました: {key}")

    def run(self) -> None:
        """メインループを実行"""
        logger.info("仮想ライトエンティティを起動しています...")

        # MQTTクライアントを起動
        self.mqtt_client.connect()

        try:
            # メインループ - 1秒ごとに状態チェックなど
            while True:
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
                    f"ライト '{light.light_id}' の制御トピックを登録: {light_topic}/set"
                )

            # 照度トピック
            brightness_topic = light.mqtt_brightness_topic
            if brightness_topic:
                self.brightness_topics[brightness_topic] = light.light_id
                logger.info(
                    f"ライト '{light.light_id}' の照度トピックを登録: {brightness_topic}"
                )

    def on_connect(self, client, userdata, flags, rc, properties=None) -> None:
        """接続時のコールバック関数"""
        super().on_connect(client, userdata, flags, rc, properties)

        # 各ライトの照度トピックを購読
        if not self.brightness_topics:
            logger.warning("照度トピックが設定されていません")
        else:
            for topic in self.brightness_topics.keys():
                logger.info(f"照度トピックを購読: {topic}")
                client.subscribe(topic)

        # 各ライトの制御トピックを購読
        if not self.light_topics:
            logger.warning("ライト制御トピックが設定されていません")
        else:
            for topic in self.light_topics.keys():
                logger.info(f"ライト制御トピックを購読: {topic}")
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
            logger.error(f"メッセージ処理中にエラーが発生しました: {e}", exc_info=True)

    def _handle_brightness_message(
        self, msg, specific_light_id: Optional[str] = None
    ) -> None:
        """照度センサーからのメッセージを処理"""
        try:
            payload = msg.payload.decode("utf-8")
            logger.info(
                f"照度データを受信: {payload}"
                + (f" (ライトID: {specific_light_id})" if specific_light_id else "")
            )

            # 文字列から数値に変換
            try:
                lux_value = float(payload)
            except ValueError:
                logger.error(f"照度データを数値に変換できませんでした: {payload}")
                return

            # ライトIDが指定されている場合はそのIDを使用
            light_id = specific_light_id

            if light_id:
                logger.info(f"照度データを処理: {lux_value}lx (ライトID: {light_id})")
                # 生の照度値をイベントで渡す
                self.core.trigger_event(
                    "brightness_changed", brightness=lux_value, light_id=light_id
                )
            else:
                logger.warning("照度データを受信しましたが、対象のライトIDが指定されていません")

        except Exception as e:
            logger.error(f"照度レベルの処理に失敗しました: {e}", exc_info=True)

    def _handle_light_set_message(self, msg, light_id: str) -> None:
        """ライト制御メッセージを処理"""
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            logger.debug(
                f"ライト制御メッセージを受信: {payload} (ライトID: {light_id})"
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
                f"不正なJSONフォーマットを受信しました: {msg.payload.decode('utf-8')}"
            )
        except Exception as e:
            logger.error(f"ライト制御コマンドの処理に失敗しました: {e}", exc_info=True)


def main():
    """メインエントリーポイント"""
    try:
        core = VirtualLightCore(CONFIG_PATH)
        core.run()
    except Exception as e:
        logger.critical(
            f"プログラム実行中に重大なエラーが発生しました: {e}", exc_info=True
        )


if __name__ == "__main__":
    main()
