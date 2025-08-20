import requests
import json
from datetime import datetime, date
from typing import List, Dict, Any, Optional
from config.settings import get_notification_settings


class WeChatNotifier:
    """企业微信通知器"""
    
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
        self.headers = {
            'Content-Type': 'application/json'
        }
    
    def send_text_message(self, content: str, mentioned_list: Optional[List[str]] = None) -> bool:
        """
        发送文本消息
        
        Args:
            content: 消息内容
            mentioned_list: 提及的用户列表
        
        Returns:
            是否发送成功
        """
        data = {
            "msgtype": "text",
            "text": {
                "content": content
            }
        }
        
        if mentioned_list:
            data["text"]["mentioned_list"] = mentioned_list
        
        try:
            response = requests.post(
                self.webhook_url,
                headers=self.headers,
                data=json.dumps(data, ensure_ascii=False),
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get("errcode") == 0
            else:
                print(f"发送消息失败，状态码: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"发送消息异常: {e}")
            return False
    
    def send_markdown_message(self, content: str) -> bool:
        """
        发送markdown消息
        
        Args:
            content: markdown格式内容
        
        Returns:
            是否发送成功
        """
        data = {
            "msgtype": "markdown",
            "markdown": {
                "content": content
            }
        }
        
        try:
            response = requests.post(
                self.webhook_url,
                headers=self.headers,
                data=json.dumps(data, ensure_ascii=False),
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get("errcode") == 0
            else:
                print(f"发送消息失败，状态码: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"发送消息异常: {e}")
            return False
    
    def send_experiment_reminder(self, experiments: List[Dict[str, Any]], 
                                reminder_type: str = "daily") -> bool:
        """
        发送实验提醒消息
        
        Args:
            experiments: 实验列表
            reminder_type: 提醒类型 ("daily", "upcoming", "urgent")
        
        Returns:
            是否发送成功
        """
        if not experiments:
            return True
        
        today = date.today()
        
        if reminder_type == "daily":
            title = f"📅 今日实验安排 ({today.strftime('%Y年%m月%d日')})"
        elif reminder_type == "upcoming":
            title = f"🔔 即将到来的实验提醒 ({today.strftime('%Y年%m月%d日')})"
        else:
            title = f"⚠️ 紧急实验提醒 ({today.strftime('%Y年%m月%d日')})"
        
        # 构建markdown内容
        content = f"## {title}\n\n"
        
        # 按日期分组
        daily_tasks = {}
        for exp in experiments:
            for step in exp["steps"]:
                date_key = step["date_str"]
                if date_key not in daily_tasks:
                    daily_tasks[date_key] = []
                daily_tasks[date_key].append({
                    "sample_batch": exp["sample_batch"],
                    "method_name": exp["method_name"],
                    "step_name": step["step_name"],
                    "description": step["description"]
                })
        
        # 按日期排序
        sorted_dates = sorted(daily_tasks.keys())
        
        for date_str in sorted_dates:
            tasks = daily_tasks[date_str]
            date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
            
            if reminder_type == "daily" and date_obj != today:
                continue
            
            # 计算距离今天的天数
            days_diff = (date_obj - today).days
            if days_diff == 0:
                date_display = "**今天**"
            elif days_diff == 1:
                date_display = "**明天**"
            elif days_diff > 1:
                date_display = f"**{days_diff}天后**"
            else:
                date_display = f"**{abs(days_diff)}天前**"
            
            content += f"### {date_display} ({date_str})\n\n"
            
            for task in tasks:
                content += f"- **{task['sample_batch']}** ({task['method_name']})\n"
                content += f"  - {task['step_name']}: {task['description']}\n\n"
        
        return self.send_markdown_message(content)
    
    def test_connection(self) -> tuple[bool, str]:
        """
        测试webhook连接
        
        Returns:
            (是否成功, 消息)
        """
        test_content = "🧪 细胞毒实验排班系统 - 连接测试成功！\n\n发送时间: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        success = self.send_text_message(test_content)
        if success:
            return True, "连接测试成功！"
        else:
            return False, "连接测试失败，请检查webhook地址是否正确"


def create_notifier() -> Optional[WeChatNotifier]:
    """
    创建通知器实例
    
    Returns:
        通知器实例或None
    """
    settings = get_notification_settings()
    
    if not settings["enabled"] or not settings["webhook_url"]:
        return None
    
    return WeChatNotifier(settings["webhook_url"])


def send_daily_report(experiments: List[Dict[str, Any]]) -> bool:
    """
    发送每日报告
    
    Args:
        experiments: 实验列表
    
    Returns:
        是否发送成功
    """
    notifier = create_notifier()
    if not notifier:
        return False
    
    return notifier.send_experiment_reminder(experiments, "daily")


def send_upcoming_reminder(experiments: List[Dict[str, Any]]) -> bool:
    """
    发送即将到来的实验提醒
    
    Args:
        experiments: 实验列表
    
    Returns:
        是否发送成功
    """
    notifier = create_notifier()
    if not notifier:
        return False
    
    return notifier.send_experiment_reminder(experiments, "upcoming")


def send_urgent_reminder(experiments: List[Dict[str, Any]]) -> bool:
    """
    发送紧急实验提醒
    
    Args:
        experiments: 实验列表
    
    Returns:
        是否发送成功
    """
    notifier = create_notifier()
    if not notifier:
        return False
    
    return notifier.send_experiment_reminder(experiments, "urgent")


def test_notification() -> tuple[bool, str]:
    """
    测试通知功能
    
    Returns:
        (是否成功, 消息)
    """
    notifier = create_notifier()
    if not notifier:
        return False, "通知功能未启用或webhook未配置"
    
    return notifier.test_connection()
