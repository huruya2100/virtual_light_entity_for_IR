"""
ライト制御モジュール
"""

import logging
import time
from typing import Dict, Any, Optional, Tuple, List, Union

from .config import Config
from .homeassistant import HomeAssistantClient
from .mqtt import MQTTPublisher

logger = logging.getLogger(__name__)


class LightController:
    """
    ライト制御クラス
    
    実際の照明機器を制御するためのロジックを実装します
    """

    def __init__(self, config: Config, home_assistant: HomeAssistantClient):
        """
        コンストラクタ
        
        Args:
            config (Config): 設定オブジェクト
            home_assistant (HomeAssistantClient): Home Assistantクライアント
        """
        self.config = config
        self.home_assistant = home_assistant
        self.state = "OFF"
        self.brightness_level = 0
        self.pending_brightness = None
        
        # MQTTクライアント設定
        self.mqtt = MQTTPublisher(self.config)
        self.light_topic = self.config.get("mqtt.topics.light_topic")
        
        # デバイス情報
        self.ir_remote_id = self.config.get("HomeAssistant.ir_remote_id")
        self.device_id = self.config.get("HomeAssistant.device_id")
        
    def _execute_script(self, script_key: str, repeat: int = 1) -> Tuple[int, str]:
        """
        設定されたスクリプトを実行
        
        Args:
            script_key (str): 実行するスクリプトのキー
            repeat (int, optional): 繰り返し回数。デフォルトは1
            
        Returns:
            Tuple[int, str]: ステータスコードとレスポンステキスト
        """
        script_name = self.config.get(f"HomeAssistant.script_name.{script_key}")
        if not script_name:
            logger.error(f"スクリプトが設定されていません: {script_key}")
            return 0, f"Script not configured: {script_key}"
            
        return self.home_assistant.call_script_service(script_name, repeat)

    def _update_state(self, new_state: Optional[str] = None, new_brightness: Optional[int] = None) -> None:
        """
        ライト状態を更新してMQTTに公開
        
        Args:
            new_state (Optional[str], optional): 新しい状態。指定しない場合は現在の状態を使用
            new_brightness (Optional[int], optional): 新しい明るさ。指定しない場合は現在の明るさを使用
        """
        if new_state:
            self.state = new_state
        
        brightness = new_brightness if new_brightness is not None else self.brightness_level
        
        # 状態を公開
        payload = {"state": self.state, "brightness": brightness}
        self.mqtt.safe_publish(f"{self.light_topic}/state", payload)
        logger.debug(f"ライト状態を更新しました: {payload}")

    def turn_on(self) -> bool:
        """
        ライトをONにする
        
        Returns:
            bool: 成功したかどうか
        """
        logger.info("ライトをONにします")
        
        if self.state == "ON":
            logger.debug("ライトは既にONです")
            return True
            
        status_code, response_text = self._execute_script("on_service")
        success = status_code == 200
        
        if success:
            logger.info("ライトをONにしました")
            self.state = "ON"
            self._update_state("ON")
        else:
            logger.error(f"ライトをONにできませんでした: {response_text}")
            
        return success

    def turn_off(self) -> bool:
        """
        ライトをOFFにする
        
        Returns:
            bool: 成功したかどうか
        """
        logger.info("ライトをOFFにします")
        
        if self.state == "OFF":
            logger.debug("ライトは既にOFFです")
            return True
            
        status_code, response_text = self._execute_script("off_service")
        success = status_code == 200
        
        if success:
            logger.info("ライトをOFFにしました")
            self.state = "OFF"
            self.brightness_level = 0
            self._update_state("OFF", 0)
        else:
            logger.error(f"ライトをOFFにできませんでした: {response_text}")
            
        return success

    def convert_brightness_to_level(self, brightness: float) -> int:
        """
        照度を明るさレベルに変換
        
        Args:
            brightness (float): 照度値
            
        Returns:
            int: 明るさレベル
        """
        lx_to_brightness = self.config.get("light.lx_to_brightness", {})
        logger.debug(f"照度変換テーブル: {lx_to_brightness}")
        
        for level, range_data in lx_to_brightness.items():
            min_val = range_data.get("min", 0)
            max_val = range_data.get("max", float('inf'))
            if min_val <= brightness < max_val:
                return int(level)
                
        # デフォルト値
        max_level = max([int(level) for level in lx_to_brightness.keys()]) if lx_to_brightness else 5
        return max_level

    def set_brightness(self, brightness_level: int) -> None:
        """
        ライトの明るさレベルを設定
        
        Args:
            brightness_level (int): 明るさレベル
        """
        self.brightness_level = brightness_level

    def real2virtual_brightness(self, new_level: int) -> None:
        """
        リアルな照度を仮想ライトエンティティに反映
        
        Args:
            new_level (int): 新しい明るさレベル
        """
        try:
            if self.state is None:
                self.state = "ON" if new_level > 0 else "OFF"

            old_level = self.brightness_level
            
            if old_level == 0 and new_level > 0:
                # OFFからONへの変更
                self.state = "ON"
            elif old_level > 0 and new_level == 0:
                # ONからOFFへの変更
                self.state = "OFF"
            
            self.set_brightness(new_level)
            self._update_state(self.state, new_level)
            
        except Exception as e:
            logger.error(f"明るさの反映に失敗しました: {e}", exc_info=True)

    def change_virtual_state_state(self, new_state: str) -> bool:
        """
        バーチャルな状態をリアルな状態に反映
        
        Args:
            new_state (str): 新しい状態 ("ON" または "OFF")
            
        Returns:
            bool: 成功したかどうか
        """
        try:
            if new_state not in ["ON", "OFF"]:
                logger.warning(f"未対応の状態です: {new_state}")
                return False
                
            old_state = self.state

            if old_state == new_state:
                logger.debug(f"状態が変更されていません: {new_state}")
                return True
            
            logger.info(f"ライトの状態を {new_state} に変更します")
            
            success = False
            if new_state == "ON":
                success = self.turn_on()
            else:  # OFF
                success = self.turn_off()
                
            if success:
                self._update_state(new_state)
                
            return success
            
        except Exception as e:
            logger.error(f"状態変更に失敗しました: {e}", exc_info=True)
            return False

    def change_virtual_state_brightness(self, new_level: int, force_update: bool = False) -> bool:
        """
        バーチャルな明るさをリアルな明るさに反映
        
        Args:
            new_level (int): 新しい明るさレベル
            force_update (bool, optional): 強制的に更新するかどうか
            
        Returns:
            bool: 成功したかどうか
        """
        try:
            old_level = self.brightness_level
            
            if old_level == new_level and not force_update:
                logger.debug(f"明るさが変更されていません: {new_level}")
                return True
            
            # ライトがOFFの場合は先にONにする
            if self.state == "OFF" and new_level > 0:
                if not self.turn_on():
                    logger.error("明るさ変更のためにライトをONにできませんでした")
                    return False
            
            script_key = None
            steps = 0
            
            if new_level > old_level:
                # 明るさを上げる
                logger.info(f"明るさを上げます: {old_level} → {new_level}")
                steps = new_level - old_level
                script_key = "brightness_up_service"
            elif new_level < old_level:
                # 明るさを下げる
                logger.info(f"明るさを下げます: {old_level} → {new_level}")
                steps = old_level - new_level
                script_key = "brightness_down_service"
            else:
                # 明るさが変わらない場合は成功とみなす
                return True
            
            if steps > 0 and script_key:
                self.brightness_level = new_level
                status_code, response_text = self._execute_script(script_key, steps)
                
                if status_code != 200:
                    logger.error(f"明るさ変更に失敗しました: {response_text}")
                    return False
                    
                logger.info(f"{steps}回の明るさ変更コマンドを送信しました")
                
                # 大きな変更の場合でも待機時間を制限
                wait_time = min(steps * 0.5, 3)
                time.sleep(wait_time)
                
                self._update_state(self.state, new_level)
                return True
            
            return False
                
        except Exception as e:
            logger.error(f"明るさ変更に失敗しました: {e}", exc_info=True)
            return False

    def change_virtual_state(self, new_state_data: Dict[str, Any]) -> bool:
        """
        バーチャルな照度と状態をリアルに反映
        
        Args:
            new_state_data (Dict[str, Any]): 新しい状態データ
            
        Returns:
            bool: 成功したかどうか
        """
        try:
            new_level = new_state_data.get("brightness")
            new_state = new_state_data.get("state", "").upper()
            
            if not new_state and new_level is None:
                logger.warning("変更する状態が指定されていません")
                return False
                
            old_state = self.state
            old_level = self.brightness_level

            # 状態と明るさの変更を最適化
            if new_state and old_state != new_state and new_level is not None and old_level != new_level:
                # 状態と明るさが変更された場合
                if not self.change_virtual_state_state(new_state):
                    return False
                    
                # 明るさまで変更するなら明るさセンサーからのデータを待つ
                self.pending_brightness = new_level
                return True
                
            elif new_state and old_state != new_state:
                # 状態だけが変わった場合
                return self.change_virtual_state_state(new_state)
                
            elif new_level is not None and (old_level != new_level or old_state == "OFF"):
                # 状態は変わらず明るさだけが変わった場合、またはOFFから特定の明るさにする場合
                return self.change_virtual_state_brightness(new_level)
                
            return True
            
        except Exception as e:
            logger.error(f"状態/明るさ変更に失敗しました: {e}", exc_info=True)
            return False
    
    # イベントハンドラメソッド
    
    def handle_brightness_change(self, brightness: float) -> None:
        """
        照度変更イベントのハンドラ
        
        Args:
            brightness (float): 新しい照度値
        """
        try:
            new_level = self.convert_brightness_to_level(brightness)
            logger.info(f"照度レベルを変換: {brightness} → {new_level}")
            
            if self.pending_brightness is not None:
                # 状態と明るさが同時に変更される場合
                logger.info(f"保留中の明るさを適用: {self.pending_brightness}")
                self.change_virtual_state_brightness(self.pending_brightness)
                self.pending_brightness = None
            else:
                self.real2virtual_brightness(new_level)
                
        except Exception as e:
            logger.error(f"照度変更の処理に失敗しました: {e}", exc_info=True)
            
    def handle_state_change(self, state: str) -> None:
        """
        状態変更イベントのハンドラ
        
        Args:
            state (str): 新しい状態
        """
        try:
            logger.info(f"状態変更を処理: {state}")
            self.change_virtual_state_state(state)
        except Exception as e:
            logger.error(f"状態変更の処理に失敗しました: {e}", exc_info=True)