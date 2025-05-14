"""
Home Assistant API通信モジュール
"""

import logging
import time
from typing import Dict, Any, Tuple, Optional, List

import requests

logger = logging.getLogger(__name__)


class HomeAssistantClient:
    """Home Assistant API通信用クライアント"""

    def __init__(self, url: str, token: str):
        """
        コンストラクタ

        Args:
            url (str): Home Assistant URL
            token (str): Home Assistant APIトークン
        """
        self.url = url
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def call_script_service(self, script_name: str, repeat: int = 1) -> Tuple[int, str]:
        """
        Home AssistantのREST APIを使用してスクリプトを実行

        Args:
            script_name (str): 実行するスクリプト名
            repeat (int, optional): 繰り返し回数。デフォルトは1

        Returns:
            Tuple[int, str]: ステータスコードとレスポンステキストのタプル
        """
        if not script_name:
            logger.warning("スクリプト名が指定されていません")
            return 0, "Script name not specified"

        logger.info(f"スクリプト実行: {script_name} (繰り返し: {repeat}回)")
        url = f"{self.url}/api/services/script/turn_on"
        payload = {"entity_id": script_name}

        response = None
        try:
            for i in range(repeat):
                response = requests.post(url, headers=self.headers, json=payload)
                if response.status_code != 200:
                    logger.warning(
                        f"APIコール失敗: {response.status_code} {response.text}"
                    )
                time.sleep(0.5)

            status_code = response.status_code if response else 0
            text = response.text if response else ""
            logger.debug(f"API レスポンス: {status_code} {text}")
            return status_code, text
        except requests.RequestException as e:
            logger.error(f"Home Assistant APIの通信エラー: {e}", exc_info=True)
            return 0, f"通信エラー: {str(e)}"
        except Exception as e:
            logger.error(
                f"Home Assistant APIの呼び出しに失敗しました: {e}", exc_info=True
            )
            return 0, str(e)

    def get_entity_state(self, entity_id: str) -> Tuple[int, Dict[str, Any]]:
        """
        エンティティの状態を取得

        Args:
            entity_id (str): エンティティID

        Returns:
            Tuple[int, Dict]: ステータスコードとエンティティ情報のタプル
        """
        logger.info(f"エンティティ状態を取得: {entity_id}")
        url = f"{self.url}/api/states/{entity_id}"

        try:
            response = requests.get(url, headers=self.headers)
            status_code = response.status_code

            if status_code == 200:
                data = response.json()
                logger.debug(f"エンティティ状態: {data}")
                return status_code, data
            else:
                logger.warning(
                    f"エンティティ状態取得失敗: {status_code} {response.text}"
                )
                return status_code, {}
        except Exception as e:
            logger.error(
                f"エンティティ状態取得中にエラーが発生しました: {e}", exc_info=True
            )
            return 0, {}

    def call_service(
        self, domain: str, service: str, service_data: Dict[str, Any]
    ) -> Tuple[int, str]:
        """
        Home Assistantのサービスを呼び出す

        Args:
            domain (str): サービスドメイン (例: "light", "switch")
            service (str): サービス名 (例: "turn_on", "turn_off")
            service_data (Dict): サービスデータ

        Returns:
            Tuple[int, str]: ステータスコードとレスポンステキストのタプル
        """
        logger.info(f"サービス呼び出し: {domain}.{service} - データ: {service_data}")
        url = f"{self.url}/api/services/{domain}/{service}"

        try:
            response = requests.post(url, headers=self.headers, json=service_data)
            status_code = response.status_code

            if status_code != 200:
                logger.warning(f"サービス呼び出し失敗: {status_code} {response.text}")

            return status_code, response.text
        except Exception as e:
            logger.error(
                f"サービス呼び出し中にエラーが発生しました: {e}", exc_info=True
            )
            return 0, str(e)

    def get_device_info(self, device_id: str) -> Tuple[int, Dict[str, Any]]:
        """
        デバイス情報を取得

        Args:
            device_id (str): デバイスID

        Returns:
            Tuple[int, Dict]: ステータスコードとデバイス情報のタプル
        """
        logger.info(f"デバイス情報を取得: {device_id}")
        url = f"{self.url}/api/config/device_registry"

        try:
            response = requests.get(url, headers=self.headers)
            status_code = response.status_code

            if status_code == 200:
                devices = response.json()
                for device in devices:
                    if device.get("id") == device_id:
                        return status_code, device
                logger.warning(f"デバイスが見つかりません: {device_id}")
                return status_code, {}
            else:
                logger.warning(f"デバイス情報取得失敗: {status_code} {response.text}")
                return status_code, {}
        except Exception as e:
            logger.error(
                f"デバイス情報取得中にエラーが発生しました: {e}", exc_info=True
            )
            return 0, {}
