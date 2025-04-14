import threading
import logging
import time
from typing import Dict, Any, Optional, List, Union
from abc import ABC, abstractmethod

from .config import Config
from .mqtt import BaseMQTTClient, MQTTPublisher
from .light_controller import LightController
from .homeassistant import HomeAssistantClient

# ロガー設定
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

CONFIG_PATH = "settings.json"


class VirtualLightCore:
    """仮想ライト制御のコアクラス"""
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.config = Config(config_path)
        self.plugins: List[Plugin] = []
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
        self.mqtt_client = MQTTVirtualLightClient(self.config, self.light_controller, self)
        
        # イベントハンドラの登録
        self.register_event_handler("brightness_changed", self.light_controller.handle_brightness_change)
        self.register_event_handler("state_changed", self.light_controller.handle_state_change)
        
        # 設定変更イベントを登録
        self.register_event_handler("config_changed", self.handle_config_changed)

    def register_plugin(self, plugin: 'Plugin') -> None:
        """プラグインを登録する"""
        plugin.init(self)
        self.plugins.append(plugin)
        logger.info(f"プラグイン '{plugin.name}' を登録しました")

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
                    logger.error(f"イベントハンドラ実行中にエラーが発生しました: {e}", exc_info=True)

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
        
        # プラグインマネージャを初期化
        from .plugins import PluginManager
        plugin_manager = PluginManager(self)
        
        # 有効なプラグインをロード
        plugin_manager.load_enabled_plugins()
        
        # すべてのプラグインを起動
        for plugin in self.plugins:
            try:
                plugin.start()
            except Exception as e:
                logger.error(f"プラグイン '{plugin.name}' の起動に失敗しました: {e}")
        
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
        
        # プラグインを停止
        for plugin in reversed(self.plugins):
            try:
                plugin.stop()
            except Exception as e:
                logger.error(f"プラグイン '{plugin.name}' の停止に失敗しました: {e}")
        
        # MQTTクライアントを停止
        self.mqtt_client.disconnect()


class Plugin(ABC):
    """プラグインの基底クラス"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """プラグイン名"""
        pass
    
    @abstractmethod
    def init(self, core: VirtualLightCore) -> None:
        """初期化"""
        pass
    
    @abstractmethod
    def start(self) -> None:
        """起動"""
        pass
    
    @abstractmethod
    def stop(self) -> None:
        """停止"""
        pass


class MQTTVirtualLightClient(BaseMQTTClient):
    """仮想ライト用MQTTクライアント"""
    def __init__(self, config: Config, light_controller: LightController, core: VirtualLightCore):
        super().__init__(config)
        self.brightness_topic = self.config.get("mqtt.topics.brightness_topic")
        self.light_topic = self.config.get("mqtt.topics.light_topic")
        self.light_controller = light_controller
        self.core = core

    def on_connect(self, client, userdata, flags, rc, properties=None) -> None:
        """接続時のコールバック関数"""
        super().on_connect(client, userdata, flags, rc, properties)
        
        # トピックの購読
        logger.info(f"トピックを購読: {self.brightness_topic}")
        client.subscribe(self.brightness_topic)
        logger.info(f"トピックを購読: {self.light_topic}/set")
        client.subscribe(self.light_topic + "/set")

    def on_message(self, client, userdata, msg) -> None:
        """MQTTメッセージ受信時のコールバック関数"""
        super().on_message(client, userdata, msg)
        
        try:
            if msg.topic == self.brightness_topic:
                self._handle_brightness_message(msg)
            elif msg.topic == self.light_topic + "/set":
                self._handle_light_set_message(msg)
        except Exception as e:
            logger.error(f"メッセージ処理中にエラーが発生しました: {e}", exc_info=True)

    def _handle_brightness_message(self, msg) -> None:
        """照度センサーからのメッセージを処理"""
        try:
            payload = msg.payload.decode("utf-8")
            logger.info(f"照度データを受信: {payload}")
            
            # 小数点以下の桁数を丸める
            brightness = round(float(payload), 1)
            
            # イベントを発火
            self.core.trigger_event("brightness_changed", brightness=brightness)
            
        except ValueError:
            logger.error(f"不正な照度データを受信しました: {payload}")
        except Exception as e:
            logger.error(f"照度レベルの処理に失敗しました: {e}", exc_info=True)

    def _handle_light_set_message(self, msg) -> None:
        """ライト制御メッセージを処理"""
        try:
            import json
            payload = json.loads(msg.payload.decode("utf-8"))
            logger.debug(f"ライト制御メッセージを受信: {payload}")
            
            # イベントを発火
            self.core.trigger_event("light_command", command=payload)
            
            has_state = "state" in payload
            has_brightness = "brightness" in payload
            
            if has_state:
                state = payload["state"].upper()
                self.core.trigger_event("state_changed", state=state)
            
            if has_brightness:
                brightness = int(payload["brightness"])
                self.core.trigger_event("brightness_level_changed", brightness_level=brightness)
                
        except json.JSONDecodeError:
            logger.error(f"不正なJSONフォーマットを受信しました: {msg.payload.decode('utf-8')}")
        except Exception as e:
            logger.error(f"ライト制御コマンドの処理に失敗しました: {e}", exc_info=True)


def main():
    """メインエントリーポイント"""
    try:
        core = VirtualLightCore(CONFIG_PATH)
        core.run()
    except Exception as e:
        logger.critical(f"プログラム実行中に重大なエラーが発生しました: {e}", exc_info=True)


if __name__ == "__main__":
    main()
