"""
自動モード切替プラグイン

時間帯に応じて自動的に明るさを調整するプラグイン
"""

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from ...main import Plugin, VirtualLightCore

logger = logging.getLogger(__name__)


class AutoModePlugin(Plugin):
    """
    自動モード切替プラグイン
    
    設定された時間帯に応じて、自動的に明るさレベルを調整します
    """
    
    @property
    def name(self) -> str:
        return "自動モード切替"
    
    def __init__(self):
        """コンストラクタ"""
        self.core = None
        self.is_running = False
        self.thread = None
        self.check_interval = 60  # 確認間隔（秒）
        self.schedule = {}
        self.auto_mode_enabled = False
    
    def init(self, core: VirtualLightCore) -> None:
        """
        プラグインの初期化
        
        Args:
            core (VirtualLightCore): コアシステム
        """
        self.core = core
        
        # 設定を読み込む
        self.auto_mode_enabled = self.core.config.get("plugins.auto_mode.enabled", False)
        self.schedule = self.core.config.get("plugins.auto_mode.schedule", {})
        self.check_interval = self.core.config.get("plugins.auto_mode.check_interval", 60)
        
        # イベントハンドラを登録
        self.core.register_event_handler("config_changed", self.handle_config_changed)
    
    def start(self) -> None:
        """プラグインを開始"""
        if self.is_running:
            return
            
        logger.info("自動モード切替プラグインを開始します")
        
        self.is_running = True
        self.thread = threading.Thread(target=self._schedule_loop, daemon=True)
        self.thread.start()
    
    def stop(self) -> None:
        """プラグインを停止"""
        if not self.is_running:
            return
            
        logger.info("自動モード切替プラグインを停止します")
        
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=5.0)
            self.thread = None
    
    def handle_config_changed(self, key: str, value: Any) -> None:
        """
        設定変更イベントのハンドラ
        
        Args:
            key (str): 変更された設定キー
            value (Any): 新しい設定値
        """
        if key == "plugins.auto_mode.enabled":
            self.auto_mode_enabled = value
            logger.info(f"自動モード: {'有効' if value else '無効'}")
        
        elif key == "plugins.auto_mode.schedule":
            self.schedule = value
            logger.info("自動モードスケジュールを更新しました")
            
        elif key == "plugins.auto_mode.check_interval":
            self.check_interval = value
            logger.info(f"確認間隔を {value} 秒に更新しました")
    
    def _schedule_loop(self) -> None:
        """スケジュール確認ループ"""
        while self.is_running:
            try:
                if self.auto_mode_enabled:
                    self._check_schedule()
            except Exception as e:
                logger.error(f"スケジュール処理中にエラーが発生しました: {e}", exc_info=True)
                
            # 次回確認まで待機
            time.sleep(self.check_interval)
    
    def _check_schedule(self) -> None:
        """
        現在時刻に合わせてスケジュールをチェックし、必要に応じてライト状態を変更
        """
        if not self.schedule:
            return
            
        # 現在時刻
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        
        # 適用するべき設定を見つける
        current_setting = None
        for time_str, setting in self.schedule.items():
            if current_time >= time_str:
                current_setting = setting
            else:
                break
        
        # 設定がない場合は処理終了
        if current_setting is None:
            return
            
        # 設定を適用
        try:
            state = current_setting.get("state")
            brightness = current_setting.get("brightness")
            
            if state or brightness is not None:
                logger.info(f"スケジュールに基づいてライト状態を変更: 時間 {current_time}, 状態 {state}, 明るさ {brightness}")
                
                # 明るさレベルまたは状態が指定されている場合は変更
                if state == "OFF":
                    self.core.light_controller.change_virtual_state_state("OFF")
                elif state == "ON":
                    if brightness is not None:
                        self.core.light_controller.change_virtual_state({"state": "ON", "brightness": brightness})
                    else:
                        self.core.light_controller.change_virtual_state_state("ON")
                elif brightness is not None:
                    self.core.light_controller.change_virtual_state_brightness(brightness)
        except Exception as e:
            logger.error(f"スケジュール適用中にエラーが発生しました: {e}", exc_info=True)