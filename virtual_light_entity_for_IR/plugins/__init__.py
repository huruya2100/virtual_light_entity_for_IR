"""
プラグイン管理モジュール
"""

import importlib
import logging
import os
import pkgutil
from typing import Dict, List, Any, Type, Optional

from ..main import Plugin, VirtualLightCore

logger = logging.getLogger(__name__)


class PluginManager:
    """プラグイン管理クラス"""
    
    def __init__(self, core: VirtualLightCore):
        """
        コンストラクタ
        
        Args:
            core (VirtualLightCore): コアシステム
        """
        self.core = core
        self.plugins: Dict[str, Plugin] = {}
        self.available_plugins: Dict[str, Type[Plugin]] = {}

    def discover_plugins(self) -> None:
        """利用可能なプラグインを検出する"""
        logger.info("プラグインを検出しています...")
        
        # プラグインパッケージのパス
        package_path = os.path.dirname(__file__)
        parent_package = __name__.rsplit(".", 1)[0] if "." in __name__ else __name__
        
        for _, name, ispkg in pkgutil.iter_modules([package_path]):
            if ispkg:  # サブパッケージのみをプラグインとして扱う
                try:
                    # プラグインモジュールをインポート
                    module_name = f"{parent_package}.{name}"
                    module = importlib.import_module(module_name)
                    
                    # プラグインクラスを検索
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if isinstance(attr, type) and issubclass(attr, Plugin) and attr != Plugin:
                            # 見つかったプラグインクラスを登録
                            plugin_class = attr
                            plugin_id = f"{name}.{attr_name}"
                            self.available_plugins[plugin_id] = plugin_class
                            logger.info(f"プラグインを検出しました: {plugin_id}")
                except Exception as e:
                    logger.error(f"プラグイン '{name}' の読み込み中にエラーが発生しました: {e}", exc_info=True)
    
    def load_plugin(self, plugin_id: str) -> bool:
        """
        プラグインをロードする
        
        Args:
            plugin_id (str): プラグインID
            
        Returns:
            bool: ロードに成功したかどうか
        """
        if plugin_id in self.plugins:
            logger.warning(f"プラグイン '{plugin_id}' は既にロードされています")
            return True
            
        if plugin_id not in self.available_plugins:
            logger.error(f"プラグイン '{plugin_id}' は利用できません")
            return False
            
        try:
            # プラグインをインスタンス化
            plugin_class = self.available_plugins[plugin_id]
            plugin = plugin_class()
            
            # コアに登録
            self.core.register_plugin(plugin)
            
            # 管理リストに追加
            self.plugins[plugin_id] = plugin
            logger.info(f"プラグイン '{plugin_id}' をロードしました")
            return True
        except Exception as e:
            logger.error(f"プラグイン '{plugin_id}' のロード中にエラーが発生しました: {e}", exc_info=True)
            return False
    
    def unload_plugin(self, plugin_id: str) -> bool:
        """
        プラグインをアンロードする
        
        Args:
            plugin_id (str): プラグインID
            
        Returns:
            bool: アンロードに成功したかどうか
        """
        if plugin_id not in self.plugins:
            logger.warning(f"プラグイン '{plugin_id}' はロードされていません")
            return False
            
        try:
            plugin = self.plugins[plugin_id]
            plugin.stop()
            
            # コアからプラグインを削除
            if plugin in self.core.plugins:
                self.core.plugins.remove(plugin)
                
            # 管理リストから削除
            del self.plugins[plugin_id]
            
            logger.info(f"プラグイン '{plugin_id}' をアンロードしました")
            return True
        except Exception as e:
            logger.error(f"プラグイン '{plugin_id}' のアンロード中にエラーが発生しました: {e}", exc_info=True)
            return False
    
    def load_enabled_plugins(self) -> None:
        """設定で有効になっているプラグインを全てロードする"""
        # まずプラグインを検出
        self.discover_plugins()
        
        # 設定から有効なプラグインを取得
        enabled_plugins = self.core.config.get("plugins.enabled", [])
        
        if not enabled_plugins:
            logger.info("有効なプラグインはありません")
            return
            
        # 有効なプラグインをロード
        for plugin_id in enabled_plugins:
            self.load_plugin(plugin_id)