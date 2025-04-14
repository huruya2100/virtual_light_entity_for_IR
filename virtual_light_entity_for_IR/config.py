"""
設定ファイル管理モジュール
"""

import json
import logging
import os
from typing import Any, Dict

logger = logging.getLogger(__name__)


class Config:
    """
    設定ファイル管理クラス
    
    設定ファイルの読み込みと設定値へのアクセスを提供します
    """

    def __init__(self, json_path: str):
        """
        コンストラクタ
        
        Args:
            json_path (str): 設定ファイルのパス
        """
        self.json_path = json_path
        self.config: Dict[str, Any] = {}
        self.last_modified_time = 0
        self.load()

    def load(self) -> bool:
        """
        設定ファイルをロードする
        ファイルが最後に読み込んだ時から変更されている場合のみ読み込みます
        
        Returns:
            bool: 読み込みに成功したかどうか
        """
        try:
            # ファイルが存在しない場合はエラー
            if not os.path.exists(self.json_path):
                logger.error(f"設定ファイルが見つかりません: {self.json_path}")
                return False
                
            # ファイルの最終更新時刻を取得
            current_mtime = os.path.getmtime(self.json_path)
            
            # ファイルが変更されていない場合は読み込まない
            if current_mtime <= self.last_modified_time:
                return True
                
            with open(self.json_path, encoding="utf-8") as f:
                json_data = f.read()
                
            self.config = json.loads(json_data)
            self.last_modified_time = current_mtime
            logger.debug(f"設定ファイルを読み込みました: {self.json_path}")
            return True
            
        except json.JSONDecodeError as e:
            logger.error(f"設定ファイルのJSONフォーマットが無効です: {e}")
            return False
        except Exception as e:
            logger.error(f"設定ファイルの読み込みに失敗しました: {e}", exc_info=True)
            return False

    def get(self, key_path: str, default: Any = None) -> Any:
        """
        指定されたキーパスの設定値を取得する
        
        Args:
            key_path (str): ドットで区切られたキーパス (例: "mqtt.host")
            default (Any, optional): キーが存在しない場合のデフォルト値
            
        Returns:
            Any: 設定値、またはキーが存在しない場合はデフォルト値
        """
        # 設定を再読み込み（変更があった場合のみ）
        self.load()

        keys = key_path.split(".")
        value = self.config
        
        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default

    def set(self, key_path: str, value: Any) -> bool:
        """
        指定されたキーパスに設定値を保存する
        
        Args:
            key_path (str): ドットで区切られたキーパス (例: "mqtt.host")
            value (Any): 設定値
            
        Returns:
            bool: 設定の保存に成功したかどうか
        """
        # 最新の設定を読み込む
        self.load()

        keys = key_path.split(".")
        target = self.config
        
        # 最後のキー以外のパスを作成
        for key in keys[:-1]:
            if key not in target:
                target[key] = {}
            if not isinstance(target[key], dict):
                target[key] = {}
            target = target[key]
            
        # 値を設定
        target[keys[-1]] = value
        
        try:
            with open(self.json_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            self.last_modified_time = os.path.getmtime(self.json_path)
            logger.debug(f"設定を保存しました: {key_path} = {value}")
            return True
        except Exception as e:
            logger.error(f"設定の保存に失敗しました: {e}", exc_info=True)
            return False
            
    def get_all(self) -> Dict[str, Any]:
        """
        全ての設定を取得する
        
        Returns:
            Dict[str, Any]: 全ての設定
        """
        self.load()
        return self.config