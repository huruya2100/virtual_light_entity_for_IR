import threading
from paho.mqtt import client as mqtt_client
import requests
import json
import logging
import time
from datetime import datetime
from typing import List, Dict, Any, Union, Tuple, Optional

# 再接続の間隔
FIRST_RECONNECT_DELAY = 1
RECONNECT_RATE = 2
MAX_RECONNECT_DELAY = 60
MAX_RECONNECT_COUNT = 5

CONFIG_PATH = "settings.json"
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s"
)


class Config:
    def __init__(self, json_path: str):
        self.json_path = json_path
        self.config: Dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        try:
            with open(self.json_path) as f:
                json_data = f.read()
            self.config = json.loads(json_data)
        except Exception as e:
            logging.error(f"設定ファイルの読み込みに失敗しました: {e}")
            self.config = {}

    def get(self, key_path: str, default: Any = None) -> Any:
        """指定されたキーパスの設定値を取得する"""
        self.load()

        keys = key_path.split(".")
        value = self.config
        try:
            for key in keys:
                value = value[key]
        except (KeyError, TypeError):
            return default
        return value

    def set(self, key_path: str, value: Any) -> None:
        """指定されたキーパスに設定値を保存する"""
        self.load()

        keys = key_path.split(".")
        target = self.config
        for key in keys[:-1]:
            if key not in target:
                target[key] = {}
            target = target[key]
        target[keys[-1]] = value
        
        try:
            with open(self.json_path, "w") as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            logging.error(f"設定の保存に失敗しました: {e}")


class BaseMQTTClient:
    """MQTTクライアントの基底クラス"""
    def __init__(self, config: Config):
        self.config = config
        self.client = None
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
        """切断時のコールバック"""
        logging.info("MQTTブローカーから切断されました")
        logging.debug(f"Client: {client}, Userdata: {userdata}, Result code: {rc}")
        if rc != 0:
            logging.error("予期せぬ切断です。再接続を試みます...")
            self.connect()

    def connect(self) -> None:
        """MQTTブローカーに接続"""
        try:
            host = self.config.get("mqtt.host")
            port = self.config.get("mqtt.port")
            self.client.connect(host, port, keepalive=60)
            self.client.loop_start()
        except Exception as e:
            logging.error(f"MQTT接続に失敗しました: {e}")

    def disconnect(self) -> None:
        """MQTTブローカーから切断"""
        try:
            logging.info("MQTTブローカーから切断します")
            self.client.disconnect()
        except Exception as e:
            logging.error(f"MQTT切断に失敗しました: {e}")

    def publish(self, topic: str, payload: str) -> None:
        """メッセージを発行"""
        try:
            logging.debug(f"メッセージを発行: {topic} {payload}")
            self.client.publish(topic, payload)
        except Exception as e:
            logging.error(f"メッセージ発行に失敗しました: {e}")

    def on_connect(self, client, userdata, flags, rc, properties=None) -> None:
        """接続時のコールバック"""
        logging.info(f"接続完了 結果コード: {rc}")
        logging.debug(
            f"Client: {client}, Userdata: {userdata}, Flags: {flags}, Properties: {properties}"
        )

    def on_message(self, client, userdata, msg) -> None:
        """メッセージ受信時のコールバック"""
        logging.info(f"メッセージ受信: {msg.topic} {msg.payload.decode('utf-8')}")
        logging.debug(f"Client: {client}, Userdata: {userdata}, Message: {msg}")


class MQTTClient(BaseMQTTClient):
    """メイン処理用MQTTクライアント"""
    def __init__(self, config: Config):
        super().__init__(config)
        self.brightness_topic = self.config.get("mqtt.topics.brightness_topic")
        self.light_topic = self.config.get("mqtt.topics.light_topic")
        self.light = Light(config)

    def on_connect(self, client, userdata, flags, rc, properties=None) -> None:
        """接続時のコールバック関数"""
        super().on_connect(client, userdata, flags, rc, properties)
        
        # トピックの購読
        logging.info(f"トピックを購読: {self.brightness_topic}")
        client.subscribe(self.brightness_topic)
        logging.info(f"トピックを購読: {self.light_topic}/set")
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
            logging.error(f"メッセージ処理中にエラーが発生しました: {e}")

    def _handle_brightness_message(self, msg) -> None:
        """照度センサーからのメッセージを処理"""
        try:
            logging.info(f"照度データを受信: {msg.payload.decode('utf-8')}")
            # 小数点以下の桁数を丸める
            brightness = round(float(msg.payload.decode("utf-8")), 1)
            new_level = self.light.convert_brightness_to_level(brightness)
            logging.info(f"新しい照度レベル: {new_level}")
            
            if self.light.pending_brightness is not None:
                # 状態と明るさが同時に変更される場合
                self.light.change_virtual_state_brightness(
                    self.light.brightness_level, self.light.pending_brightness
                )
                publish_payload = {
                    "state": "ON",
                    "brightness": self.light.pending_brightness,
                }
                self.publish(
                    self.light_topic + "/state", json.dumps(publish_payload)
                )
                self.light.pending_brightness = None
            else:
                self.light.real2virtual_brightness(new_level)
        except Exception as e:
            logging.error(f"照度レベルの更新に失敗しました: {e}")

    def _handle_light_set_message(self, msg) -> None:
        """ライト制御メッセージを処理"""
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            logging.debug(f"ペイロード: {payload}")
            
            has_state = "state" in payload
            has_brightness = "brightness" in payload
            
            if has_state and has_brightness:
                self.light.change_virtual_state(payload)
            elif has_state:
                self.light.change_virtual_state_state(payload["state"].upper())
            elif has_brightness:
                self.light.change_virtual_state_brightness(payload["brightness"])
        except Exception as e:
            logging.error(f"ライト状態の変更に失敗しました: {e}")

    def run(self) -> None:
        """メインループ実行"""
        self.connect()
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            logging.info("プログラムが中断されました")
        finally:
            self.disconnect()


class MQTTPublisher(BaseMQTTClient):
    """発行専用MQTTクライアント"""
    def __init__(self, config: Config):
        super().__init__(config)


class HomeAssistantClient:
    """Home Assistant API通信用クライアント"""
    def __init__(self, url: str, token: str):
        self.url = url
        self.token = token

    def call_script_service(self, script_name: str, repeat: int = 1) -> Tuple[int, str]:
        """
        Home AssistantのREST APIを使ってスクリプトを実行する関数

        :param script_name: スクリプト名
        :param repeat: 繰り返し回数
        :return: ステータスコードとレスポンステキストのタプル
        """
        logging.info(f"スクリプト実行: {script_name} (繰り返し: {repeat}回)")
        url = f"{self.url}/api/services/script/turn_on"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        payload = {"entity_id": script_name}
        
        response = None
        try:
            for i in range(repeat):
                response = requests.post(url, headers=headers, json=payload)
                time.sleep(0.5)
            
            status_code = response.status_code if response else 0
            text = response.text if response else ""
            logging.debug(f"API レスポンス: {status_code} {text}")
            return status_code, text
        except Exception as e:
            logging.error(f"Home Assistant APIの呼び出しに失敗しました: {e}")
            return 0, str(e)


class Light:
    """バーチャルライト管理クラス"""
    def __init__(self, config: Config, state: Optional[str] = None, brightness_level: Optional[int] = None):
        self.config = config
        self.state = state
        self.brightness_level = brightness_level
        self.brightness_level_step = len(self.config.get("light.lx_to_brightness", {}))
        self.pending_brightness = None

        # Home Assistantクライアント設定
        ha_url = self.config.get("HomeAssistant.url")
        ha_token = self.config.get("HomeAssistant.token")
        self.home_assistant = HomeAssistantClient(ha_url, ha_token)
        self.ir_remote_id = self.config.get("HomeAssistant.ir_remote_id")
        
        # MQTTクライアント設定
        self.light_topic = self.config.get("mqtt.topics.light_topic")
        self.mqtt = MQTTPublisher(self.config)

    def turn_on(self) -> None:
        """ライトをONにする"""
        logging.info("ライトをONにします")
        script_name = self.config.get("HomeAssistant.script_name.on_service")
        status_code, response_text = self.home_assistant.call_script_service(script_name)
        logging.info(f"ライトをONにしました。レスポンス: {status_code}, {response_text}")
        self.state = "ON"

    def turn_off(self) -> None:
        """ライトをOFFにする"""
        logging.info("ライトをOFFにします")
        script_name = self.config.get("HomeAssistant.script_name.off_service")
        status_code, response_text = self.home_assistant.call_script_service(script_name)
        logging.info(f"ライトをOFFにしました。レスポンス: {status_code}, {response_text}")
        self.state = "OFF"

    def convert_brightness_to_level(self, brightness: float) -> int:
        """照度を明るさレベルに変換する"""
        lx_to_brightness = self.config.get("light.lx_to_brightness", {})
        logging.debug(f"照度変換テーブル: {lx_to_brightness}")
        
        for level, range_data in lx_to_brightness.items():
            min_val = range_data.get("min", 0)
            max_val = range_data.get("max", float('inf'))
            if min_val <= brightness < max_val:
                return int(level)
        return 5  # デフォルト値

    def set_brightness(self, brightness_level: int) -> None:
        """ライトの明るさを設定する"""
        self.brightness_level = brightness_level

    def real2virtual_brightness(self, new_level: int) -> None:
        """リアルな照度を仮想ライトエンティティに反映する"""
        try:
            self.mqtt.connect()
            
            if self.state is None:
                self.state = "ON" if new_level > 0 else "OFF"

            old_level = self.brightness_level
            
            if old_level == 0 or new_level == 0:
                self.state = "OFF" if new_level == 0 else "ON"
            
            self.set_brightness(new_level)
            
            msg = {"state": self.state, "brightness": new_level}
            self.mqtt.publish(self.light_topic + "/state", json.dumps(msg))
        except Exception as e:
            logging.error(f"明るさの反映に失敗しました: {e}")
        finally:
            self.mqtt.disconnect()

    def change_virtual_state_state(self, new_state: str) -> None:
        """バーチャルなon/off状態をリアルな状態に反映する"""
        try:
            old_state = self.state

            if old_state is not None and old_state == new_state:
                return  # 状態が同じなら何もしない
            
            logging.info(f"ライトの状態を {new_state} に変更します")
            
            if new_state == "ON":
                self.turn_on()
            elif new_state == "OFF":
                self.turn_off()

            payload = {"state": new_state, "brightness": self.brightness_level}
            self.mqtt.connect()
            self.mqtt.publish(self.light_topic + "/state", json.dumps(payload))
        except Exception as e:
            logging.error(f"状態変更に失敗しました: {e}")
        finally:
            self.mqtt.disconnect()

    def change_virtual_state_brightness(self, new_level: int) -> None:
        """バーチャルな照度をリアルな照度に反映する"""
        try:
            old_level = self.brightness_level
            
            if new_level > old_level:
                # 明るさを上げる
                logging.info("明るさを上げます")
                steps = new_level - old_level
                self.brightness_level = new_level
                script_name = self.config.get("HomeAssistant.script_name.brightness_up_service")
                status_code, response_text = self.home_assistant.call_script_service(script_name, steps)
                logging.info(f"{steps}回の明るさ上げコマンドを送信しました。レスポンス: {status_code}, {response_text}")
                time.sleep(5)
            elif new_level < old_level:
                # 明るさを下げる
                logging.info("明るさを下げます")
                steps = old_level - new_level
                self.brightness_level = new_level
                script_name = self.config.get("HomeAssistant.script_name.brightness_down_service")
                status_code, response_text = self.home_assistant.call_script_service(script_name, steps)
                logging.info(f"{steps}回の明るさ下げコマンドを送信しました。レスポンス: {status_code}, {response_text}")
                time.sleep(5)

            self.mqtt.connect()
            payload = {"state": self.state, "brightness": new_level}
            self.mqtt.publish(self.light_topic + "/state", json.dumps(payload))
        except Exception as e:
            logging.error(f"明るさ変更に失敗しました: {e}")
        finally:
            self.mqtt.disconnect()

    def change_virtual_state(self, new_state_data: Dict[str, Any]) -> None:
        """バーチャルな照度と状態をリアルに反映する"""
        try:
            old_level = self.brightness_level
            new_level = new_state_data["brightness"]

            old_state = self.state.upper() if self.state else "OFF"
            new_state = new_state_data["state"].upper()

            if old_state == new_state and old_level != new_level:
                # 状態は変わらず明るさだけが変わった場合
                self.change_virtual_state_brightness(new_level)
            elif old_state != new_state and old_level == new_level:
                # 状態だけが変わった場合
                self.change_virtual_state_state(new_state)
            elif old_state != new_state and old_level != new_level:
                # 状態と明るさが変更された場合
                self.change_virtual_state_state(new_state)
                # 明るさまで変更するなら明るさセンサーからのデータを待つ
                self.pending_brightness = new_level
        except Exception as e:
            logging.error(f"状態/明るさ変更に失敗しました: {e}")


if __name__ == "__main__":
    try:
        config = Config(CONFIG_PATH)
        mqtt = MQTTClient(config)
        mqtt.run()
    except Exception as e:
        logging.critical(f"プログラム実行中に重大なエラーが発生しました: {e}")
