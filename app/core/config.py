"""配置管理器"""

import os
import toml
from pathlib import Path
from typing import Dict, Any


class ConfigManager:
    """配置管理器"""

    def __init__(self) -> None:
        """初始化"""

        # 加载环境变量
        self.config_path: Path = Path(__file__).parents[2] / "data" / "setting.toml"
        self.global_config: Dict[str, Any] = self.load("global")
        self.grok_config: Dict[str, Any] = self.load("grok")
        self._storage = None

    def set_storage(self, storage) -> None:
        """设置存储实例"""
        self._storage = storage

    def load(self, section: str) -> Dict[str, Any]:
        """配置加载器 - 优先从环境变量读取，然后从配置文件读取"""
        try:
            # 首先尝试从配置文件加载
            config = {}
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = toml.load(f).get(section, {})
            except FileNotFoundError:
                print(f"[Setting] 配置文件不存在，使用环境变量和默认值: {self.config_path}")
            
            # 环境变量映射表
            env_mappings = {
                "global": {
                    "base_url": "BASE_URL",
                    "log_level": "LOG_LEVEL",
                    "image_mode": "IMAGE_MODE",
                    "admin_password": "ADMIN_PASSWORD",
                    "admin_username": "ADMIN_USERNAME",
                    "image_cache_max_size_mb": "IMAGE_CACHE_MAX_SIZE_MB",
                    "video_cache_max_size_mb": "VIDEO_CACHE_MAX_SIZE_MB",
                },
                "grok": {
                    "api_key": "GROK_API_KEY",
                    "proxy_url": "PROXY_URL",
                    "cache_proxy_url": "CACHE_PROXY_URL",
                    "cf_clearance": "CF_CLEARANCE",
                    "x_statsig_id": "X_STATSIG_ID",
                    "filtered_tags": "FILTERED_TAGS",
                    "stream_chunk_timeout": "STREAM_CHUNK_TIMEOUT",
                    "stream_total_timeout": "STREAM_TOTAL_TIMEOUT",
                    "stream_first_response_timeout": "STREAM_FIRST_RESPONSE_TIMEOUT",
                    "temporary": "TEMPORARY",
                    "show_thinking": "SHOW_THINKING",
                }
            }
            
            # 从环境变量覆盖配置
            if section in env_mappings:
                for config_key, env_key in env_mappings[section].items():
                    env_value = os.getenv(env_key)
                    if env_value is not None:
                        # 处理布尔值
                        if config_key in ["temporary", "show_thinking"]:
                            config[config_key] = env_value.lower() in ("true", "1", "yes", "on")
                        # 处理数字值
                        elif config_key in ["stream_chunk_timeout", "stream_total_timeout",
                                          "stream_first_response_timeout", "image_cache_max_size_mb",
                                          "video_cache_max_size_mb"]:
                            try:
                                config[config_key] = int(env_value)
                            except ValueError:
                                print(f"[Setting] 环境变量 {env_key} 的值 '{env_value}' 无法转换为整数，使用默认值")
                        else:
                            config[config_key] = env_value

            # 自动将 SOCKS5 转换为 SOCKS5H
            if section == "grok" and "proxy_url" in config:
                proxy_url = config["proxy_url"]
                if proxy_url and proxy_url.startswith("socks5://"):
                    config["proxy_url"] = proxy_url.replace("socks5://", "socks5h://", 1)

            # 自动为 CF Clearance 添加前缀
            if section == "grok" and "cf_clearance" in config:
                cf_clearance = config["cf_clearance"]
                if cf_clearance and not cf_clearance.startswith("cf_clearance="):
                    config["cf_clearance"] = f"cf_clearance={cf_clearance}"

            return config
        except Exception as e:
            raise Exception(f"[Setting] 配置加载失败: {e}")
    
    async def reload(self) -> None:
        """重新加载配置（用于从存储同步后）"""
        self.global_config = self.load("global")
        self.grok_config = self.load("grok")

    async def save(self, global_config: Dict[str, Any] = None, grok_config: Dict[str, Any] = None) -> None:
        """保存配置到存储"""
        if not self._storage:
            # 如果没有设置存储，使用传统文件保存方式
            import aiofiles
            async with aiofiles.open(self.config_path, "r", encoding="utf-8") as f:
                content = await f.read()
                config = toml.loads(content)
            
            if global_config:
                config["global"].update(global_config)
            if grok_config:
                # 处理 cf_clearance，移除前缀后保存
                processed_grok_config = grok_config.copy()
                if "cf_clearance" in processed_grok_config:
                    cf_clearance = processed_grok_config["cf_clearance"]
                    if cf_clearance and cf_clearance.startswith("cf_clearance="):
                        processed_grok_config["cf_clearance"] = cf_clearance.replace("cf_clearance=", "", 1)
                config["grok"].update(processed_grok_config)
            
            async with aiofiles.open(self.config_path, "w", encoding="utf-8") as f:
                await f.write(toml.dumps(config))
        else:
            # 使用存储抽象层
            config_data = await self._storage.load_config()
            
            if global_config:
                config_data["global"].update(global_config)
            if grok_config:
                # 处理 cf_clearance，移除前缀后保存
                processed_grok_config = grok_config.copy()
                if "cf_clearance" in processed_grok_config:
                    cf_clearance = processed_grok_config["cf_clearance"]
                    if cf_clearance and cf_clearance.startswith("cf_clearance="):
                        processed_grok_config["cf_clearance"] = cf_clearance.replace("cf_clearance=", "", 1)
                config_data["grok"].update(processed_grok_config)
            
            await self._storage.save_config(config_data)
        
        # 重新加载配置
        await self.reload()
    
    def get_service_proxy(self) -> str:
        """获取服务代理URL（用于 client 和 upload）"""
        return self.grok_config.get("proxy_url", "")
    
    def get_cache_proxy(self) -> str:
        """获取缓存代理URL（用于 cache）
        
        逻辑：
        - 如果只设置了 proxy_url，缓存和服务都使用 proxy_url
        - 如果同时设置了 proxy_url 和 cache_proxy_url，缓存使用 cache_proxy_url
        """
        cache_proxy = self.grok_config.get("cache_proxy_url", "")
        service_proxy = self.grok_config.get("proxy_url", "")
        
        # 如果设置了 cache_proxy_url，优先使用
        if cache_proxy:
            return cache_proxy
        
        # 否则使用 proxy_url（服务代理）
        return service_proxy

# 全局设置
setting = ConfigManager()

if __name__ == "__main__":
    print(setting.global_config)
    print(setting.grok_config)