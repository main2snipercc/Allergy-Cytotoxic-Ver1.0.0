import threading
import time
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Callable
from config.settings import get_notification_settings, update_notification_settings
from utils.notification import send_daily_report


class NotificationScheduler:
    """通知调度器"""
    
    def __init__(self):
        self.running = False
        self.thread = None
        self.stop_event = threading.Event()
        self.experiments_data = []
        self.parse_date_func = None
        self.is_workday_func = None
        self.get_holiday_info_func = None
    
    def start(self, experiments: List[Dict[str, Any]], 
              parse_date_func: Callable = None,
              is_workday_func: Callable = None,
              get_holiday_info_func: Callable = None):
        """启动定时任务"""
        if self.running:
            print("定时任务已在运行中")
            return
        
        self.experiments_data = experiments
        self.parse_date_func = parse_date_func
        self.is_workday_func = is_workday_func
        self.get_holiday_info_func = get_holiday_info_func
        
        self.running = True
        self.stop_event.clear()
        
        self.thread = threading.Thread(
            target=self._run_scheduler,
            daemon=True
        )
        self.thread.start()
        print("定时任务已启动")
    
    def stop(self):
        """停止定时任务"""
        if not self.running:
            return
        
        self.running = False
        self.stop_event.set()
        
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)
        
        print("定时任务已停止")
    
    def update_experiments(self, experiments: List[Dict[str, Any]]):
        """更新实验数据"""
        self.experiments_data = experiments
    
    def _run_scheduler(self):
        """运行定时任务循环"""
        while self.running and not self.stop_event.is_set():
            try:
                # 获取当前设置
                settings = get_notification_settings()
                
                if settings["enabled"] and settings["webhook_url"]:
                    current_time = datetime.now()
                    today_str = current_time.strftime("%Y-%m-%d")
                    
                    # 检查是否需要推送
                    should_send = self._should_send_notification(settings, current_time, today_str)
                    
                    # 调试日志：每小时输出一次状态
                    if current_time.minute == 0:
                        print(f"调度器状态检查 - {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
                        print(f"  推送启用: {settings['enabled']}")
                        print(f"  Webhook配置: {'已配置' if settings['webhook_url'] else '未配置'}")
                        print(f"  推送时间: {settings['push_time']}")
                        print(f"  上次推送: {settings['last_push_date']}")
                        print(f"  今日是否需要推送: {should_send}")
                        print(f"  数据记录数: {len(self.experiments_data)}")
                    
                    if should_send:
                        print(f"开始执行每日推送任务 - {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
                        print(f"  数据记录数: {len(self.experiments_data)}")
                        print(f"  Webhook: {settings['webhook_url'][:50]}...")
                        
                        # 执行推送
                        success = send_daily_report(self.experiments_data)
                        
                        if success:
                            # 更新最后推送日期
                            update_notification_settings(last_push_date=today_str)
                            print(f"✅ 每日推送任务完成 - {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
                        else:
                            print(f"❌ 每日推送任务失败 - {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
                
                # 每分钟检查一次
                self.stop_event.wait(60)
                
            except Exception as e:
                print(f"定时任务执行出错: {e}")
                import traceback
                print(traceback.format_exc())
                # 出错后等待一段时间再继续
                self.stop_event.wait(300)  # 等待5分钟
    
    def _should_send_notification(self, settings: Dict[str, Any], 
                                 current_time: datetime, today_str: str) -> bool:
        """判断是否应该发送通知"""
        # 检查是否已经发送过今天的通知
        if settings["last_push_date"] == today_str:
            return False
        
        # 检查是否到了推送时间
        try:
            push_time = datetime.strptime(settings["push_time"], "%H:%M").time()
            current_time_only = current_time.time()
            
            # 在推送时间前后5分钟内发送
            time_diff = abs((current_time_only.hour * 60 + current_time_only.minute) - 
                           (push_time.hour * 60 + push_time.minute))
            
            return time_diff <= 5
            
        except ValueError:
            print(f"推送时间格式错误: {settings['push_time']}")
            return False
    
    def send_manual_notification(self, notification_type: str = "daily") -> bool:
        """手动发送通知"""
        if not self.experiments_data:
            print("没有实验数据可发送")
            return False
        
        try:
            if notification_type == "daily":
                success = send_daily_report(self.experiments_data)
            else:
                print(f"不支持的通知类型: {notification_type}")
                return False
            
            if success:
                print(f"✅ 今日实验内容发送成功")
                return True
            else:
                print(f"❌ 今日实验内容发送失败")
                return False
                
        except Exception as e:
            print(f"发送通知异常: {e}")
            return False


# 全局调度器实例
_scheduler = NotificationScheduler()


def start_notification_scheduler(experiments: List[Dict[str, Any]], 
                               parse_date_func: Callable = None,
                               is_workday_func: Callable = None,
                               get_holiday_info_func: Callable = None):
    """启动通知调度器"""
    _scheduler.start(experiments, parse_date_func, is_workday_func, get_holiday_info_func)


def stop_notification_scheduler():
    """停止通知调度器"""
    _scheduler.stop()


def is_scheduler_running():
    """检查调度器是否在运行"""
    return _scheduler.running


def update_scheduler_experiments(experiments: List[Dict[str, Any]]):
    """更新调度器中的实验数据"""
    _scheduler.update_experiments(experiments)


def send_manual_notification(notification_type: str = "daily"):
    """手动发送今日实验内容"""
    return _scheduler.send_manual_notification(notification_type)
