"""
OmniStream Pro - Settings Manager
Centralized settings management with database persistence and live callbacks.
Author: XMON4U (https://github.com/Xmon4u)
"""

import os
import shutil
from typing import Any, Dict, Callable, List, Tuple, Optional
from database import get_setting, set_setting, get_all_settings

DEFAULT_SAVE_DIR = os.path.join(
    os.environ.get("USERPROFILE") or os.path.expanduser("~"),
    "Downloads",
    "videos"
)

DEFAULTS = {
    "max_concurrent": 3,                     # 1, 2, 3, 5, 0 (0 = unlimited)
    "speed_limit": "unlimited",               # 'unlimited', '2M', '5M', '10M', 'custom'
    "custom_speed_limit_mbps": 5.0,
    "default_save_dir": DEFAULT_SAVE_DIR,
    "smart_organization": False,             # Movies/ & TV Shows/ folder auto-sorting
    "queue_completion_action": "none",        # 'none', 'sound', 'sleep', 'shutdown'
    "minimize_to_tray_on_close": True,
    "auto_retry_enabled": True,
    "max_retries": 3,
    "retry_backoff": [5, 15, 30],
    "notification_sound": True,
    "duplicate_detection": True,
    "min_disk_space_gb": 2.0,                # Minimum free storage warning threshold
}

_LISTENERS: List[Callable[[str, Any], None]] = []


class SettingsManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SettingsManager, cls).__new__(cls)
            cls._instance._cached = {}
            cls._instance.reload()
        return cls._instance

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_all(self) -> Dict[str, Any]:
        return dict(self._cached)

    def update(self, new_dict: Dict[str, Any]):
        for k, v in new_dict.items():
            self.set(k, v)

    def reload(self):
        """Load settings from database and populate defaults."""
        try:
            db_settings = get_all_settings()
        except Exception:
            db_settings = {}
        self._cached = dict(DEFAULTS)
        self._cached.update(db_settings)

    def get(self, key: str, default: Any = None) -> Any:
        return self._cached.get(key, default if default is not None else DEFAULTS.get(key))

    def set(self, key: str, value: Any):
        self._cached[key] = value
        set_setting(key, value)
        for cb in _LISTENERS:
            try:
                cb(key, value)
            except Exception:
                pass

    def add_listener(self, callback: Callable[[str, Any], None]):
        if callback not in _LISTENERS:
            _LISTENERS.append(callback)

    def remove_listener(self, callback: Callable[[str, Any], None]):
        if callback in _LISTENERS:
            _LISTENERS.remove(callback)

    def get_speed_limit_arg(self) -> Optional[str]:
        """Convert speed limit setting to N_m3u8DL-RE --max-speed parameter value."""
        lim = str(self.get("speed_limit", "unlimited")).lower()
        if lim in ("unlimited", "none", "0"):
            return None
        if lim == "custom":
            val = float(self.get("custom_speed_limit_mbps", 5.0))
            return f"{val:.1f}M"
        return lim.upper()

    def check_disk_space(self, target_dir: str, min_free_gb: Optional[float] = None) -> Tuple[bool, float, float]:
        """
        Check if target directory has at least min_disk_space_gb available.
        Returns: (is_ok, free_gb, total_gb)
        """
        try:
            path = target_dir if os.path.exists(target_dir) else os.path.dirname(target_dir)
            if not os.path.exists(path):
                path = os.path.expanduser("~")
            total, used, free = shutil.disk_usage(path)
            free_gb = free / (1024 ** 3)
            total_gb = total / (1024 ** 3)
            min_gb = float(min_free_gb) if min_free_gb is not None else float(self.get("min_disk_space_gb", 2.0))
            return (free_gb >= min_gb, free_gb, total_gb)
        except Exception:
            return (True, 999.0, 999.0)


settings = SettingsManager()
