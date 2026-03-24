"""
IRコマンド送信モジュール

Home AssistantスクリプトまたはTasmota MQTTを使用してIRコマンドを送信します。
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Tuple

if TYPE_CHECKING:
    from config import Config
    from homeassistant import HomeAssistantClient
    from mqtt import MQTTPublisher

logger = logging.getLogger(__name__)


class IRSenderBase(ABC):
    """IRコマンド送信の基底クラス"""

    @abstractmethod
    def send_command(self, command_key: str, repeat: int = 1) -> Tuple[int, str]:
        """
        IRコマンドを送信

        Args:
            command_key (str): コマンドキー (例: "on_service", "off_service")
            repeat (int): 繰り返し回数

        Returns:
            Tuple[int, str]: ステータスコードとメッセージ
        """


class HomeAssistantIRSender(IRSenderBase):
    """Home AssistantスクリプトでIRコマンドを送信するクラス"""

    def __init__(
        self,
        light_id: str,
        light_prefix: str,
        config: "Config",
        home_assistant: "HomeAssistantClient",
    ):
        self.light_id = light_id
        self.light_prefix = light_prefix
        self.config = config
        self.home_assistant = home_assistant

    def send_command(self, command_key: str, repeat: int = 1) -> Tuple[int, str]:
        script_name = self.config.get(f"{self.light_prefix}.script_name.{command_key}")

        if not script_name:
            logger.error(
                "スクリプトが設定されていません: %s (ライトID: %s)",
                command_key,
                self.light_id,
            )
            return 0, f"Script not configured: {command_key}"

        return self.home_assistant.call_script_service(script_name, repeat)


class TasmotaIRSender(IRSenderBase):
    """Tasmota MQTTを使用してIRコマンドを送信するクラス"""

    def __init__(
        self,
        light_id: str,
        light_prefix: str,
        config: "Config",
        mqtt: "MQTTPublisher",
    ):
        self.light_id = light_id
        self.light_prefix = light_prefix
        self.config = config
        self.mqtt = mqtt

    def send_command(self, command_key: str, repeat: int = 1) -> Tuple[int, str]:
        tasmota_topic = self.config.get(f"{self.light_prefix}.tasmota.topic")
        ir_command = self.config.get(
            f"{self.light_prefix}.tasmota.ir_commands.{command_key}"
        )

        if not tasmota_topic:
            logger.error(
                "Tasmotaトピックが設定されていません (ライトID: %s)", self.light_id
            )
            return 0, "Tasmota topic not configured"

        if not ir_command:
            logger.error(
                "IRコマンドが設定されていません: %s (ライトID: %s)",
                command_key,
                self.light_id,
            )
            return 0, f"IR command not configured: {command_key}"

        topic = f"cmnd/{tasmota_topic}/IRsend"

        try:
            for i in range(repeat):
                self.mqtt.publish(topic, ir_command)
                if i < repeat - 1:
                    time.sleep(0.5)

            logger.info(
                "TasmotaにIRコマンドを送信しました: %s × %s (ライトID: %s)",
                command_key,
                repeat,
                self.light_id,
            )
            return 200, "OK"
        except Exception as e:
            logger.error("Tasmota IRコマンド送信に失敗しました: %s", e, exc_info=True)
            return 0, str(e)


def create_ir_sender(
    light_id: str,
    light_prefix: str,
    config: "Config",
    home_assistant: "HomeAssistantClient",
    mqtt: "MQTTPublisher",
) -> IRSenderBase:
    """
    設定に基づいてIRセンダーを生成

    Args:
        light_id (str): ライトID
        light_prefix (str): 設定キープレフィックス
        config (Config): 設定オブジェクト
        home_assistant (HomeAssistantClient): Home Assistantクライアント
        mqtt (MQTTPublisher): MQTTパブリッシャー

    Returns:
        IRSenderBase: IRセンダーインスタンス
    """
    sender_type = config.get(f"{light_prefix}.ir_sender") or "homeassistant"

    if sender_type == "tasmota":
        logger.info("ライト '%s' にTasmota IRセンダーを使用します", light_id)
        return TasmotaIRSender(light_id, light_prefix, config, mqtt)
    else:
        logger.info("ライト '%s' にHome Assistant IRセンダーを使用します", light_id)
        return HomeAssistantIRSender(light_id, light_prefix, config, home_assistant)
