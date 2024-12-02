import threading
from paho.mqtt import client as mqtt_client
import requests
import json
import logging
import time
from datetime import datetime
from typing import List, Dict, Any, Union, Tuple

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
    def __init__(self, json_path):
        self.json_path = json_path
        self.load()

    def load(self):
        with open(self.json_path) as f:
            json_data = f.read()
        self.config = json.loads(json_data)

    def get(self, key_path, default=None):
        self.load()

        keys = key_path.split(".")
        value = self.config
        try:
            for key in keys:
                value = value[key]
        except KeyError:
            return default
        return value

    def set(self, key_path, value):
        self.load()

        keys = key_path.split(".")
        target = self.config
        for key in keys[:-1]:
            target = target[key]
        target[keys[-1]] = value
        with open(self.json_path, "w") as f:
            json.dump(self.config, f, indent=4)


class MQTTClient:
    def __init__(self, config):
        self.config = config

        self.brightness_topic = self.config.get("mqtt.topics.brightness_topic")
        self.light_topic = self.config.get("mqtt.topics.light_topic")

        self.light = Light(config)
        self.client = mqtt_client.Client(
            client_id="", userdata=None, protocol=mqtt_client.MQTTv5, transport="tcp"
        )

        username = self.config.get("mqtt.username")
        password = self.config.get("mqtt.password")
        if isinstance(username, str) and isinstance(password, str):
            self.client.username_pw_set(username, password)

        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect

    def on_disconnect(self, client, userdata, rc, properties=None):
        logging.info("Disconnected from MQTT broker")
        logging.debug("Client: %s, Userdata: %s, Result code: %s", client, userdata, rc)
        if rc != 0:
            logging.error("Unexpected disconnection. Reconnecting...")
            self.connect()

    def connect(self):
        host = self.config.get("mqtt.host")
        port = self.config.get("mqtt.port")
        self.client.connect(host, port, keepalive=60)
        self.client.loop_start()

    def disconnect(self):
        logging.info("Disconnecting from MQTT main broker")
        self.client.disconnect()

    def on_connect(self, client, userdata, flags, rc, properties=None) -> None:
        """
        接続時のコールバック関数

        :param client: MQTTクライアント
        :param userdata: ユーザデータ
        :param flags: フラグ
        :param rc: 結果コード
        :param properties: プロパティ
        """
        logging.info("Connected with result code %s", rc)
        logging.debug(
            "Client: %s, Userdata: %s, Flags: %s, Properties: %s",
            client,
            userdata,
            flags,
            properties,
        )
        logging.info("Subscribing to topics: %s", self.brightness_topic)
        client.subscribe(self.brightness_topic)
        logging.info("Subscribing to topics: %s", self.light_topic + "/set")
        client.subscribe(self.light_topic + "/set")

    def publish(self, topic, payload):
        logging.debug("Publishing message: %s %s", topic, payload)
        self.client.publish(topic, payload)

    def on_message(self, client, userdata, msg):
        """
        MQTTメッセージを受信したときのコールバック関数

        :param client: MQTTクライアント
        :param userdata: ユーザデータ
        :param msg: 受信したメッセージ
        """
        logging.info("Message received: %s %s", msg.topic, msg.payload.decode("utf-8"))
        logging.debug("Client: %s, Userdata: %s, Message: %s", client, userdata, msg)
        if msg.topic == self.brightness_topic:
            """
            センサーからの照度が変更になったとき。brightness_topicに照度が送られてくる
            """
            try:
                logging.info("Received brightness: %s", msg.payload.decode("utf-8"))
                # 小数点以下の桁数を丸める
                brightness = round(float(msg.payload.decode("utf-8")), 1)
                new_level = self.light.convert_brightness_to_level(brightness)
                logging.info("New brightness level: %s", new_level)
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
                logging.error("Failed to update brightness level: %s", e)
        elif msg.topic == self.light_topic + "/set":
            # stateの変更
            payload = json.loads(msg.payload.decode("utf-8"))
            logging.debug("Payload: %s", payload)
            if "state" in payload and "brightness" in payload:
                self.light.change_virtual_state(payload)
            elif "state" in payload and "brightness" not in payload:
                self.light.change_virtual_state_state(payload["state"].upper())
            elif "state" not in payload and "brightness" in payload:
                self.light.change_virtual_state_brightness(payload["brightness"])

    def run(self):
        self.connect()
        while True:
            time.sleep(60)  # 10 minutes
            #self.publish(self.light_topic + "/state", json.dumps({"state": self.light.state, "brightness": self.light.brightness_level}))



class MQTTClient_publish:
    def __init__(self, config):
        self.config = config
        self.client = mqtt_client.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def on_connect(self, client, userdata, flags, rc):
        logging.info("Connected with result code %s", rc)

    def on_message(self, client, userdata, msg):
        """
        MQTTメッセージを受信したときのコールバック関数

        :param client: MQTTクライアント
        :param userdata: ユーザデータ
        :param msg: 受信したメッセージ
        """
        logging.info("Message received: %s %s", msg.topic, msg.payload.decode())

    def connect(self):
        host = self.config.get("mqtt.host")
        port = self.config.get("mqtt.port")
        self.client.connect(host, port, keepalive=60)
        self.client.loop_start()

    def disconnect(self):
        logging.info("Disconnecting from MQTT Publish broker")
        self.client.disconnect()

    def publish(self, topic, payload):
        logging.debug("Publishing message: %s %s", topic, payload)
        self.client.publish(topic, payload)


class Light:
    def __init__(self, config, state=None, brightness_level=None):
        self.config = config

        # on, off, night_light
        self.state = state
        # 0-5
        self.brightness_level = brightness_level
        self.brightness_level_step = int(len(self.config.get("light.lx_to_brightness")))

        ha_url = self.config.get("HomeAssistant.url")
        ha_token = self.config.get("HomeAssistant.token")
        self.home_assistant = HomeAssistantClient(ha_url, ha_token)

        self.ir_remote_id = self.config.get("HomeAssistant.ir_remote_id")
        self.light_topic = self.config.get("mqtt.topics.light_topic")
        self.mqtt = MQTTClient_publish(self.config)
        self.pending_brightness = None

    def turn_on(self):
        # スクリプトを実行してライトをONにする
        logging.info("Turning on the light")
        script_name = self.config.get("HomeAssistant.script_name.on_service")
        status_code, response_text = self.home_assistant.call_script_service(
            script_name
        )
        logging.info(f"Turned on the light. Response: {status_code}, {response_text}")
        self.state = "ON"

    def turn_off(self):
        # スクリプトを実行してライトをOFFにする
        logging.info("Turning off the light")
        script_name = self.config.get("HomeAssistant.script_name.off_service")
        status_code, response_text = self.home_assistant.call_script_service(
            script_name
        )
        print(f"Turned off the light. Response: {status_code}, {response_text}")
        self.state = "OFF"

    def convert_brightness_to_level(self, brightness):
        """
        照度を明るさレベルに変換する関数
        """
        lx_to_brightness = self.config.get("light.lx_to_brightness")
        logging.debug("lx_to_brightness: %s", lx_to_brightness)
        for level, range in lx_to_brightness.items():
            min = range["min"]
            max = range["max"]
            if min <= brightness and brightness < max:
                return int(level)
        return 5

    def set_brightness(self, brightness_level):
        """
        ライトの状態と明るさを設定する関数

        """
        self.brightness_level = brightness_level


    def real2virtual_brightness(self, new_level):
        """
        リアルな照度を仮想ライトエンティティに反映する関数

        """
        self.mqtt.connect()
        if self.state is None:
            if new_level > 0:
                self.state = "ON"
            elif new_level == 0:
                self.state = "OFF"

        old_level = self.brightness_level
        msg = ""
        if old_level == 0 or new_level == 0:
            # 現在の状態が0または新しい状態が0の場合
            if new_level == 0:
                self.state = "OFF"
            elif old_level == 0:
                self.state = "ON"
        topic = self.light_topic + "/state"

        self.set_brightness(new_level)
        msg = {"state": self.state, "brightness": new_level}
        self.mqtt.publish(topic, json.dumps(msg))
        self.mqtt.disconnect()
        return

    def change_virtual_state_state(self, new_state: str):
        """
        バーチャルなon/off状態をリアルな状態に反映する関数
        """
        old_state = self.state

        if old_state is not None:
            if old_state == new_state:
                return
        else:
            # 初回の状態設定
            old_state = new_state

        logging.info("Changing the light state to %s", new_state)
        if new_state == "ON":
            self.turn_on()
        elif new_state == "OFF":
            self.turn_off()

        payload = {"state": new_state, "brightness": self.brightness_level}
        self.mqtt.connect()
        self.mqtt.publish(self.light_topic + "/state", json.dumps(payload))
        self.mqtt.disconnect()
        return

    def change_virtual_state_brightness(self, new_level: int):
        """
        バーチャルな照度をリアルな照度に反映する関数

        params:
        old_level: int: 現在の照度
        new_level: int: 新しい照度
        """
        old_level = self.brightness_level

        """

        if old_level == 0 or new_level == 0:
            if new_level == 0:
                self.turn_off()
            elif old_level == 0:
                self.turn_on()
        """

        if new_level > old_level:
            # 明るさを上げる
            logging.info("Increasing brightness")
            steps = new_level - old_level
            self.brightness_level = new_level
            script_name = self.config.get("HomeAssistant.script_name.brightness_up_service")
            status_code, response_text = self.home_assistant.call_script_service(
                script_name, steps
            )
            
            logging.info(
                f"Sent {steps} brightness up commands. Response: {status_code}, {response_text}"
            )
            time.sleep(5)

        elif new_level < old_level:
            # 明るさを下げる
            logging.info("Decreasing brightness")
            steps = old_level - new_level
            self.brightness_level = new_level
            script_name = self.config.get("HomeAssistant.script_name.brightness_down_service")
            status_code, response_text = self.home_assistant.call_script_service(
                script_name, steps
            )
            logging.info(
                f"Sent {steps} brightness down commands. Response: {status_code}, {response_text}"
            )
            time.sleep(5)


        self.mqtt.connect()
        payload = {"state": self.state, "brightness": new_level}
        self.mqtt.publish(self.light_topic + "/state", json.dumps(payload))
        self.mqtt.disconnect()

        return

    def change_virtual_state(self, new_state: Dict[str, Any]):
        """
        バーチャルな照度をリアルな照度に反映する関数

        """

        old_level = self.brightness_level
        new_level = new_state["brightness"]

        old_state = self.state.upper()
        new_state = new_state["state"].upper()

        if old_state == new_state and old_level != new_level:
            # 状態は変わらず明るさだけが変わった場合
            self.change_virtual_state_brightness(new_level)
        elif old_state != new_state and old_level == new_level:
            # 状態だけが変わった場合
            self.change_virtual_state_state(new_state)
        elif old_state != new_state and old_level != new_level:
            # 状態と明るさが変更された場合
            self.change_virtual_state_state(new_state)
            # 明るさまで変更するなら明るさセンサーからのデータを待つ必要がある
            self.pending_brightness = new_level
        return


class HomeAssistantClient:
    def __init__(self, url, token):
        self.url = url
        self.token = token

    def call_script_service(self, script_name: str, repeat=1) -> Tuple[int, str]:
        """
        Home AssistantのREST APIを使ってスクリプトを実行する関数

        :param script_name: スクリプト名
        :return: ステータスコードとレスポンステキストのタプル
        """
        logging.info("Calling script service: %s", script_name)
        url = f"{self.url}/api/services/script/turn_on"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        payload = {"entity_id": script_name}
        for i in range(repeat):
            response = requests.post(url, headers=headers, json=payload)
            time.sleep(0.5)
        logging.debug(f"API Response: {response.status_code} {response.text}")
        return response.status_code, response.text


if __name__ == "__main__":
    config = Config(CONFIG_PATH)
    mqtt = MQTTClient(config)
    mqtt.run()
