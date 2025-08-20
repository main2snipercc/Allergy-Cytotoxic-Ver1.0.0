import json
import os
from pathlib import Path
from datetime import datetime, time

# 配置文件路径
CONFIG_DIR = Path("config")
CONFIG_FILE = CONFIG_DIR / "user_settings.json"

# 细胞毒检测方法配置
CYTOTOXIC_METHODS = {
    "7天计数增值度法": {
        "name": "7天计数增值度法",
        "steps": [
            {"day": 1, "action": "上样", "description": "第一天上样"},
            {"day": 2, "action": "换液", "description": "第二天换液"},
            {"day": 4, "action": "2天计数", "description": "第四天2天计数"},
            {"day": 6, "action": "4天计数", "description": "第六天4天计数"},
            {"day": 9, "action": "7天计数", "description": "第九天7天计数"}
        ]
    },
    "USP显微镜法": {
        "name": "USP显微镜法",
        "steps": [
            {"day": 1, "action": "上样", "description": "第一天上样"},
            {"day": 2, "action": "换液", "description": "第二天换液"},
            {"day": 4, "action": "2天观察", "description": "第四天2天观察"}
        ]
    },
    "MTT-GB14233.2": {
        "name": "MTT-GB14233.2",
        "steps": [
            {"day": 1, "action": "上样", "description": "第一天上样"},
            {"day": 2, "action": "换液", "description": "第二天换液"},
            {"day": 5, "action": "观察MTT结果", "description": "第五天观察MTT结果"}
        ]
    },
    "MTT-ISO等同16886": {
        "name": "MTT-ISO等同16886",
        "steps": [
            {"day": 1, "action": "上样", "description": "第一天上样"},
            {"day": 2, "action": "换液", "description": "第二天换液"},
            {"day": 3, "action": "观察MTT结果", "description": "第三天观察MTT结果"}
        ]
    },
    "日本药局方": {
        "name": "日本药局方",
        "steps": [
            {"day": 1, "action": "上样", "description": "第一天上样"},
            {"day": 2, "action": "换液", "description": "第二天换液"},
            {"day": 9, "action": "计数", "description": "第九天计数（可选9-11天）"},
            {"day": 10, "action": "计数", "description": "第十天计数（可选9-11天）"},
            {"day": 11, "action": "计数", "description": "第十一天计数（可选9-11天）"}
        ]
    }
}

# 默认配置
DEFAULT_SETTINGS = {
    "notification": {
        "enabled": False,
        "webhook_url": "",
        "push_time": "08:00",
        "last_push_date": "",
        "reminder_days": [1, 2, 3]  # 提前提醒的天数
    },
    "display": {
        "show_weekends": False,
        "highlight_today": True,
        "color_scheme": "default"
    }
}


def ensure_config_dir():
    """确保配置目录存在"""
    CONFIG_DIR.mkdir(exist_ok=True)


def load_settings():
    """加载用户设置"""
    ensure_config_dir()
    
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                settings = json.load(f)
            
            # 合并默认设置，确保所有必要的键都存在
            merged_settings = DEFAULT_SETTINGS.copy()
            for key, value in settings.items():
                if key in merged_settings:
                    if isinstance(merged_settings[key], dict) and isinstance(value, dict):
                        merged_settings[key].update(value)
                    else:
                        merged_settings[key] = value
                else:
                    merged_settings[key] = value
            
            return merged_settings
            
        except Exception as e:
            print(f"加载配置文件失败: {e}")
            return DEFAULT_SETTINGS.copy()
    else:
        return DEFAULT_SETTINGS.copy()


def save_settings(settings):
    """保存用户设置"""
    ensure_config_dir()
    
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"保存配置文件失败: {e}")
        return False


def get_notification_settings():
    """获取通知相关设置"""
    settings = load_settings()
    return settings.get("notification", DEFAULT_SETTINGS["notification"])


def update_notification_settings(enabled=None, webhook_url=None, push_time=None, 
                               last_push_date=None, reminder_days=None):
    """更新通知设置"""
    settings = load_settings()
    notification = settings.get("notification", DEFAULT_SETTINGS["notification"].copy())
    
    if enabled is not None:
        notification["enabled"] = enabled
    if webhook_url is not None:
        notification["webhook_url"] = webhook_url
    if push_time is not None:
        notification["push_time"] = push_time
    if last_push_date is not None:
        notification["last_push_date"] = last_push_date
    if reminder_days is not None:
        notification["reminder_days"] = reminder_days
    
    settings["notification"] = notification
    return save_settings(settings)


def get_display_settings():
    """获取显示相关设置"""
    settings = load_settings()
    return settings.get("display", DEFAULT_SETTINGS["display"])


def update_display_settings(show_weekends=None, highlight_today=None, color_scheme=None):
    """更新显示设置"""
    settings = load_settings()
    display = settings.get("display", DEFAULT_SETTINGS["display"].copy())
    
    if show_weekends is not None:
        display["show_weekends"] = show_weekends
    if highlight_today is not None:
        display["highlight_today"] = highlight_today
    if color_scheme is not None:
        display["color_scheme"] = color_scheme
    
    settings["display"] = display
    return save_settings(settings)


def validate_webhook_url(webhook_url):
    """验证企业微信webhook地址格式"""
    if not webhook_url:
        return False, "Webhook地址不能为空"
    
    if not webhook_url.startswith("https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key="):
        return False, "请输入正确的企业微信机器人Webhook地址"
    
    return True, "地址格式正确"


def validate_time_format(time_str):
    """验证时间格式 (HH:MM)"""
    try:
        time.fromisoformat(time_str)
        return True, "时间格式正确"
    except ValueError:
        return False, "请输入正确的时间格式 (HH:MM)"


def get_cytotoxic_methods():
    """获取所有细胞毒检测方法"""
    return CYTOTOXIC_METHODS


def get_method_steps(method_name):
    """获取指定方法的实验步骤"""
    return CYTOTOXIC_METHODS.get(method_name, {}).get("steps", [])
