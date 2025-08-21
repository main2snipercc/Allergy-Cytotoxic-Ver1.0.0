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
        "adjustable": False,  # 不能调整
        "steps": [
            {"day": 1, "action": "上样", "description": "第一天上样", "adjustable": False},
            {"day": 2, "action": "换液", "description": "第二天换液", "adjustable": False},
            {"day": 4, "action": "2天计数", "description": "第四天2天计数", "adjustable": False},
            {"day": 6, "action": "4天计数", "description": "第六天4天计数", "adjustable": False},
            {"day": 9, "action": "7天计数", "description": "第九天7天计数", "adjustable": False}
        ]
    },
    "USP显微镜法": {
        "name": "USP显微镜法",
        "adjustable": False,  # 不能调整
        "steps": [
            {"day": 1, "action": "上样", "description": "第一天上样", "adjustable": False},
            {"day": 2, "action": "换液", "description": "第二天换液", "adjustable": False},
            {"day": 4, "action": "2天观察", "description": "第四天2天观察", "adjustable": False}
        ]
    },
    "MTT-GB14233.2": {
        "name": "MTT-GB14233.2",
        "adjustable": False,  # 不能调整
        "steps": [
            {"day": 1, "action": "上样", "description": "第一天上样", "adjustable": False},
            {"day": 2, "action": "换液", "description": "第二天换液", "adjustable": False},
            {"day": 5, "action": "观察MTT结果", "description": "第五天观察MTT结果", "adjustable": False}
        ]
    },
    "MTT-ISO等同16886": {
        "name": "MTT-ISO等同16886",
        "adjustable": False,  # 不能调整
        "steps": [
            {"day": 1, "action": "上样", "description": "第一天上样", "adjustable": False},
            {"day": 2, "action": "换液", "description": "第二天换液", "adjustable": False},
            {"day": 3, "action": "观察MTT结果", "description": "第三天观察MTT结果", "adjustable": False}
        ]
    },
    "日本药局方": {
        "name": "日本药局方",
        "adjustable": True,  # 可以调整
        "steps": [
            {"day": 1, "action": "上样", "description": "第一天上样", "adjustable": False},  # 前2天不能调整
            {"day": 2, "action": "换液", "description": "第二天换液", "adjustable": False},  # 前2天不能调整
            {"day": 9, "action": "计数", "description": "第9-11天选择一天计数", "adjustable": True, "flexible_days": [9, 10, 11]}  # 最后1天在9-11天中选择
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
        "last_push_time": ""
    },
    "display": {
        "show_weekends": False,
        "highlight_today": True,
        "color_scheme": "default"
    },
    "scheduling": {
        "adjust_workdays": True  # 是否自动调整到工作日
    },
    "scheduler": {
        "running": False,  # 调度器运行状态
        "auto_start": False  # 是否自动启动调度器
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
                               last_push_date=None, last_push_time=None):
    """更新通知设置"""
    try:
        print(f"🔧 update_notification_settings 调试信息：")
        print(f"  参数: enabled={enabled}, webhook_url={webhook_url}, push_time={push_time}")
        print(f"  参数: last_push_date={last_push_date}, last_push_time={last_push_time}")
        
        settings = load_settings()
        print(f"  settings 加载成功")
        
        notification = settings.get("notification", DEFAULT_SETTINGS["notification"].copy())
        print(f"  notification 获取成功: {notification}")
        
        if enabled is not None:
            notification["enabled"] = enabled
        if webhook_url is not None:
            notification["webhook_url"] = webhook_url
        if push_time is not None:
            notification["push_time"] = push_time
        if last_push_date is not None:
            notification["last_push_date"] = last_push_date
        if last_push_time is not None:
            notification["last_push_time"] = last_push_time
        
        print(f"  notification 更新后: {notification}")
        
        settings["notification"] = notification
        result = save_settings(settings)
        print(f"  save_settings 结果: {result}")
        return result
    except Exception as e:
        print(f"❌ update_notification_settings 异常: {e}")
        import traceback
        print(traceback.format_exc())
        raise


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


def update_settings(new_settings):
    """更新用户设置"""
    ensure_config_dir()
    
    try:
        # 加载现有设置
        current_settings = load_settings()
        
        # 合并新设置
        for key, value in new_settings.items():
            if key in current_settings and isinstance(current_settings[key], dict) and isinstance(value, dict):
                current_settings[key].update(value)
            else:
                current_settings[key] = value
        
        # 保存到文件
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(current_settings, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"更新配置文件失败: {e}")
        return False


def get_scheduler_settings():
    """获取调度器相关设置"""
    settings = load_settings()
    return settings.get("scheduler", DEFAULT_SETTINGS["scheduler"])


def update_scheduler_settings(running=None, auto_start=None):
    """更新调度器设置"""
    settings = load_settings()
    scheduler = settings.get("scheduler", DEFAULT_SETTINGS["scheduler"].copy())
    
    if running is not None:
        scheduler["running"] = running
    if auto_start is not None:
        scheduler["auto_start"] = auto_start
    
    settings["scheduler"] = scheduler
    return save_settings(settings)


def is_scheduler_enabled():
    """检查调度器是否已启用（基于配置）"""
    settings = load_settings()
    scheduler = settings.get("scheduler", DEFAULT_SETTINGS["scheduler"])
    return scheduler.get("running", False)
