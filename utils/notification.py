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
        
        # 专门处理当天实验内容
        if reminder_type == "daily":
            # 只显示今天的实验
            today_tasks = []
            for exp in experiments:
                for step in exp["steps"]:
                    if step.get("date_str"):
                        date_obj = datetime.strptime(step["date_str"], "%Y-%m-%d").date()
                        if date_obj == today:
                            today_tasks.append({
                                "sample_batch": exp["sample_batch"],
                                "method_name": exp["method_name"],
                                "step_name": step["step_name"],
                                "description": step["description"],
                                "start_date": exp.get("start_date", ""),
                                "end_date": exp.get("end_date", "")
                            })
            
            if not today_tasks:
                content = f"## {title}\n\n"
                content += "**今日暂无实验安排**\n\n"
                content += "🎉 今天可以休息一下，或者安排其他工作。"
                return self.send_markdown_message(content)
            else:
                # 分批发送通知
                return self._send_daily_tasks_in_batches(title, today_tasks)
        else:
            # 处理其他类型的提醒（保持原有逻辑）
            content = f"## {title}\n\n"
            
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
    
    def _send_daily_tasks_in_batches(self, title: str, today_tasks: List[Dict[str, Any]]) -> bool:
        """
        分批发送每日实验任务
        
        Args:
            title: 消息标题
            today_tasks: 今日实验任务列表
        
        Returns:
            是否全部发送成功
        """
        try:
            # 企业微信消息长度限制（约2048字符，留一些余量）
            MAX_MESSAGE_LENGTH = 2000
            
            # 按样本批次分组
            batch_groups = {}
            for task in today_tasks:
                batch = task["sample_batch"]
                if batch not in batch_groups:
                    batch_groups[batch] = []
                batch_groups[batch].append(task)
            
            # 计算总任务数
            total_tasks = len(today_tasks)
            
            # 如果任务数量很少，直接发送一条消息
            if total_tasks <= 3:
                content = f"## {title}\n\n"
                content += f"**今日共有 {total_tasks} 个实验步骤需要执行：**\n\n"
                
                for batch, tasks in batch_groups.items():
                    content += f"### 🧪 样本批次: {batch}\n\n"
                    for task in tasks:
                        content += f"**实验方法**: {task['method_name']}\n"
                        content += f"**实验步骤**: {task['step_name']}\n"
                        content += f"**详细说明**: {task['description']}\n"
                        if task.get("start_date") and task.get("end_date"):
                            content += f"**实验周期**: {task['start_date']} 至 {task['end_date']}\n"
                        content += "\n"
                
                return self.send_markdown_message(content)
            
            # 任务数量较多，分批发送
            batch_count = 0
            success_count = 0
            
            # 发送第一条消息（概览）
            overview_content = f"## {title}\n\n"
            overview_content += f"**今日共有 {total_tasks} 个实验步骤需要执行**\n\n"
            overview_content += f"**样本批次数量**: {len(batch_groups)}\n\n"
            overview_content += "📋 详细内容将分批发送..."
            
            if self.send_markdown_message(overview_content):
                success_count += 1
            
            # 分批发送详细内容
            current_batch_content = ""
            current_batch_count = 0
            
            for batch, tasks in batch_groups.items():
                batch_content = f"### 🧪 样本批次: {batch}\n\n"
                
                for task in tasks:
                    task_content = f"**实验方法**: {task['method_name']}\n"
                    task_content += f"**实验步骤**: {task['step_name']}\n"
                    task_content += f"**详细说明**: {task['description']}\n"
                    if task.get("start_date") and task.get("end_date"):
                        task_content += f"**实验周期**: {task['start_date']} 至 {task['end_date']}\n"
                    task_content += "\n"
                    
                    # 检查是否超出长度限制
                    if len(current_batch_content + batch_content + task_content) > MAX_MESSAGE_LENGTH:
                        # 发送当前批次
                        if current_batch_content.strip():
                            batch_title = f"## {title} - 第{batch_count + 1}部分\n\n"
                            full_content = batch_title + current_batch_content
                            
                            if self.send_markdown_message(full_content):
                                success_count += 1
                                batch_count += 1
                        
                        # 开始新的批次
                        current_batch_content = batch_content + task_content
                        current_batch_count = 1
                    else:
                        current_batch_content += batch_content + task_content
                        current_batch_count += 1
                
                # 检查是否需要发送当前批次
                if len(current_batch_content) > MAX_MESSAGE_LENGTH * 0.8:  # 80%阈值
                    batch_title = f"## {title} - 第{batch_count + 1}部分\n\n"
                    full_content = batch_title + current_batch_content
                    
                    if self.send_markdown_message(full_content):
                        success_count += 1
                        batch_count += 1
                    
                    current_batch_content = ""
                    current_batch_count = 0
            
            # 发送最后一批（如果有剩余内容）
            if current_batch_content.strip():
                batch_title = f"## {title} - 第{batch_count + 1}部分\n\n"
                full_content = batch_title + current_batch_content
                
                if self.send_markdown_message(full_content):
                    success_count += 1
                    batch_count += 1
            
            # 发送完成消息
            if batch_count > 1:
                completion_content = f"## {title} - 发送完成\n\n"
                completion_content += f"✅ 今日实验内容已全部发送完成\n\n"
                completion_content += f"📊 发送统计：\n"
                completion_content += f"- 总任务数：{total_tasks}\n"
                completion_content += f"- 分批数量：{batch_count}\n"
                completion_content += f"- 成功发送：{success_count}\n"
                
                self.send_markdown_message(completion_content)
            
            # 返回是否全部发送成功
            return success_count >= batch_count
            
        except Exception as e:
            print(f"分批发送通知时出错: {e}")
            return False
    
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
