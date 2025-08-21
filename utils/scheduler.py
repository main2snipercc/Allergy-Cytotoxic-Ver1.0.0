import threading
import time
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Callable
from config.settings import get_notification_settings, update_notification_settings, update_scheduler_settings
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
            print("⚠️ 定时任务已在运行中")
            return
        
        print(f"🚀 正在启动定时任务...")
        print(f"  实验数据数量: {len(experiments)}")
        print(f"  解析日期函数: {'已配置' if parse_date_func else '未配置'}")
        print(f"  工作日检查函数: {'已配置' if is_workday_func else '未配置'}")
        print(f"  节假日信息函数: {'已配置' if get_holiday_info_func else '未配置'}")
        
        self.experiments_data = experiments
        self.parse_date_func = parse_date_func
        self.is_workday_func = is_workday_func
        self.get_holiday_info_func = get_holiday_info_func
        
        self.running = True
        self.stop_event.clear()
        
        # 持久化调度器状态
        update_scheduler_settings(running=True)
        
        # 记录启动时间，防止启动后立即推送
        self.start_time = datetime.now()
        print(f"  启动时间: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        self.thread = threading.Thread(
            target=self._run_scheduler,
            daemon=True
        )
        self.thread.start()
        print("✅ 定时任务已启动")
    
    def stop(self):
        """停止定时任务"""
        if not self.running:
            print("ℹ️ 定时任务未在运行")
            return
        
        print("🛑 正在停止定时任务...")
        self.running = False
        self.stop_event.set()
        
        # 持久化调度器状态
        update_scheduler_settings(running=False)
        
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)
            if self.thread.is_alive():
                print("⚠️ 线程未能在5秒内停止")
            else:
                print("✅ 线程已停止")
        
        print("✅ 定时任务已停止")
    
    def update_experiments(self, experiments: List[Dict[str, Any]]):
        """更新实验数据"""
        self.experiments_data = experiments
    
    def force_reset(self):
        """强制重置调度器状态，用于时间变更后的重启"""
        print(f"🔄 强制重置调度器状态")
        
        # 重置推送日期
        from config.settings import update_notification_settings
        update_notification_settings(last_push_date="")
        
        # 如果正在运行，先停止
        if self.running:
            self.stop()
            # 等待一下确保完全停止
            time.sleep(1)
        
        # 重置内部状态
        self.running = False
        self.stop_event.clear()
        
        print(f"✅ 调度器状态已重置")
        return True
    
    def check_time_changed(self, new_push_time: str):
        """检查推送时间是否被修改，如果修改了则重置推送日期和调度器"""
        from config.settings import get_notification_settings, update_notification_settings
        
        current_settings = get_notification_settings()
        if current_settings.get("push_time") != new_push_time:
            print(f"🔄 检测到推送时间变更: {current_settings.get('push_time')} -> {new_push_time}")
            print(f"🔄 重置推送状态，允许按照新时间发送")
            
            # 重置推送日期
            update_notification_settings(last_push_date="")
            
            # 如果调度器正在运行，需要重启以应用新时间
            if self.running:
                print(f"🔄 检测到时间变更，需要重启调度器以应用新设置")
                # 这里不直接重启，而是通知调用方需要重启
                return True
            return True
        return False
    
    def _run_scheduler(self):
        """运行定时任务循环"""
        print(f"🚀 调度器主循环已启动 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        while self.running and not self.stop_event.is_set():
            try:
                # 获取当前设置
                settings = get_notification_settings()
                
                if settings["enabled"] and settings["webhook_url"]:
                    current_time = datetime.now()
                    today_str = current_time.strftime("%Y-%m-%d")
                    
                    # 检查是否需要推送（只针对自动推送）
                    should_send = self._should_send_auto_notification(settings, current_time, today_str)
                    
                    # 调试日志：每10分钟输出一次状态
                    if current_time.minute % 10 == 0 and current_time.second < 30:
                        print(f"📊 调度器状态检查 - {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
                        print(f"  推送启用: {settings['enabled']}")
                        print(f"  Webhook配置: {'已配置' if settings['webhook_url'] else '未配置'}")
                        print(f"  推送时间: {settings['push_time']}")
                        print(f"  上次推送: {settings['last_push_date']}")
                        print(f"  今日是否需要推送: {should_send}")
                        print(f"  数据记录数: {len(self.experiments_data)}")
                        print(f"  调度器状态: 运行中")
                    
                    if should_send:
                        print(f"🚀 开始执行每日推送任务 - {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
                        print(f"  数据记录数: {len(self.experiments_data)}")
                        print(f"  Webhook: {settings['webhook_url'][:50]}...")
                        
                        # 执行推送
                        success = send_daily_report(self.experiments_data)
                        
                        if success:
                            # 更新推送记录：日期和时间
                            update_notification_settings(
                                last_push_date=today_str,
                                last_push_time=settings["push_time"]
                            )
                            print(f"✅ 每日推送任务完成 - {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
                            print(f"⏳ 推送完成，继续运行等待下次推送时间")
                            # 不再自动停止调度器，让它继续运行等待下次推送
                        else:
                            print(f"❌ 每日推送任务失败 - {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
                            # 推送失败不更新日期，下次检查时重试
                else:
                    # 如果通知未启用，每10分钟输出一次状态
                    if current_time.minute % 10 == 0 and current_time.second < 10:
                        print(f"⚠️ 调度器运行中但通知未启用 - {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
                        print(f"  推送启用: {settings['enabled']}")
                        print(f"  Webhook配置: {'已配置' if settings['webhook_url'] else '未配置'}")
                
                # 每10秒检查一次（提高精度，确保能精确捕获推送时间窗口）
                # 静默等待，避免输出Stopping信息
                if self.stop_event.wait(10):
                    # 如果收到停止信号，退出循环
                    break
                
            except Exception as e:
                print(f"❌ 定时任务执行出错: {e}")
                import traceback
                print(traceback.format_exc())
                # 出错后等待一段时间再继续
                self.stop_event.wait(300)  # 等待5分钟
    
    def _should_send_auto_notification(self, settings: Dict[str, Any], 
                                       current_time: datetime, today_str: str) -> bool:
        """判断是否应该发送自动通知"""
        print(f"🔍 检查自动推送条件 - 当前时间: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  设置推送时间: {settings['push_time']}")
        print(f"  上次推送日期: {settings['last_push_date']}")
        print(f"  今日日期: {today_str}")
        
        # 检查今天是否已经按照当前时间设置推送过
        # 如果时间设置变更了，允许重新推送
        if settings["last_push_date"] == today_str:
            # 检查推送时间是否变更
            last_push_time = settings.get("last_push_time", "")
            current_push_time = settings["push_time"]
            
            if last_push_time == current_push_time:
                print(f"⏭️ 今天已经按照当前时间设置({current_push_time})推送过，跳过推送")
                return False
            else:
                print(f"🔄 检测到推送时间变更: {last_push_time} -> {current_push_time}")
                print(f"🔄 允许按照新时间重新推送")
                # 不阻止推送，让时间检查逻辑继续
        
        # 检查是否到了推送时间
        try:
            push_time = datetime.strptime(settings["push_time"], "%H:%M").time()
            
            # 创建今天的推送时间点
            push_datetime = datetime.combine(current_time.date(), push_time)
            
            # 推送时间窗口：推送时间点前后30秒内（更精确）
            time_window_start = push_datetime - timedelta(seconds=30)
            time_window_end = push_datetime + timedelta(seconds=30)
            
            # 防止启动后立即推送：启动后至少等待1分钟
            if hasattr(self, 'start_time'):
                time_since_start = current_time - self.start_time
                if time_since_start.total_seconds() < 60:
                    remaining_seconds = 60 - time_since_start.total_seconds()
                    print(f"⏳ 调度器刚启动，等待 {int(remaining_seconds)} 秒后再检查推送条件")
                    return False
            
            # 推送逻辑优化：
            # 1. 在推送时间窗口内才推送
            # 2. 避免精确时间匹配的问题
            # 3. 防止启动后立即推送
            
            if current_time < time_window_start:
                # 时间还没到推送窗口
                time_diff = time_window_start - current_time
                if time_diff.total_seconds() > 60:
                    minutes_to_wait = int(time_diff.total_seconds() / 60)
                    print(f"⏳ 时间还没到推送窗口，还需等待 {minutes_to_wait} 分钟")
                else:
                    seconds_to_wait = int(time_diff.total_seconds())
                    print(f"⏳ 时间还没到推送窗口，还需等待 {seconds_to_wait} 秒")
                return False
            elif time_window_start <= current_time <= time_window_end:
                # 在推送时间窗口内，可以推送
                print(f"✅ 在推送时间窗口内，执行推送")
                print(f"  推送窗口: {time_window_start.strftime('%H:%M:%S')} - {time_window_end.strftime('%H:%M:%S')}")
                print(f"  当前时间: {current_time.strftime('%H:%M:%S')}")
                return True
            else:
                # 已经过了推送窗口，今天不再推送
                print(f"⏰ 已过推送窗口，今天不再推送")
                print(f"  推送窗口: {time_window_start.strftime('%H:%M:%S')} - {time_window_end.strftime('%H:%M:%S')}")
                print(f"  明天 {push_time.strftime('%H:%M')} 将按新设置推送")
                return False
            
        except ValueError:
            print(f"❌ 推送时间格式错误: {settings['push_time']}")
            return False
    
    def send_manual_notification(self, notification_type: str = "daily") -> bool:
        """手动发送通知 - 无时间限制，可随时推送"""
        if not self.experiments_data:
            print("没有实验数据可发送")
            return False
        
        try:
            current_time = datetime.now()
            print(f"🚀 执行手动推送 - {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"  数据记录数: {len(self.experiments_data)}")
            
            if notification_type == "daily":
                success = send_daily_report(self.experiments_data)
            else:
                print(f"不支持的通知类型: {notification_type}")
                return False
            
            if success:
                print(f"✅ 手动推送成功 - 不会影响自动推送时间记录")
                return True
            else:
                print(f"❌ 手动推送失败")
                return False
                
        except Exception as e:
            print(f"手动推送异常: {e}")
            return False


# 全局调度器实例
_scheduler = NotificationScheduler()
_scheduler_lock = threading.Lock()  # 添加线程锁防止重复启动


class SchedulerManager:
    """调度器管理器 - 统一管理调度器的启动、停止和状态"""
    
    @staticmethod
    def safe_start_scheduler(experiments: List[Dict[str, Any]], 
                           parse_date_func: Callable = None,
                           is_workday_func: Callable = None,
                           get_holiday_info_func: Callable = None,
                           force_restart: bool = False) -> bool:
        """安全启动调度器，防止重复启动"""
        with _scheduler_lock:
            try:
                # 检查调度器是否已经在运行
                if _scheduler.running and not force_restart:
                    print("⚠️ 调度器已在运行中，跳过启动")
                    return True
                
                # 如果需要强制重启，先停止现有调度器
                if force_restart and _scheduler.running:
                    print("🔄 强制重启调度器...")
                    _scheduler.stop()
                    time.sleep(1)  # 等待调度器完全停止
                
                # 检查通知设置
                from config.settings import get_notification_settings
                settings = get_notification_settings()
                
                if not settings["enabled"]:
                    print("ℹ️ 通知未启用，不启动调度器")
                    return False
                
                if not settings["webhook_url"]:
                    print("⚠️ 未配置Webhook地址，不启动调度器")
                    return False
                
                # 启动调度器
                print("🚀 启动调度器...")
                _scheduler.start(experiments, parse_date_func, is_workday_func, get_holiday_info_func)
                print("✅ 调度器启动成功")
                return True
                
            except Exception as e:
                print(f"❌ 调度器启动失败: {e}")
                return False
    
    @staticmethod
    def safe_stop_scheduler() -> bool:
        """安全停止调度器"""
        with _scheduler_lock:
            try:
                if not _scheduler.running:
                    print("ℹ️ 调度器未在运行")
                    return True
                
                print("🛑 停止调度器...")
                _scheduler.stop()
                print("✅ 调度器停止成功")
                return True
                
            except Exception as e:
                print(f"❌ 调度器停止失败: {e}")
                return False
    
    @staticmethod
    def get_scheduler_status() -> bool:
        """获取调度器真实状态"""
        return _scheduler.running
    
    @staticmethod
    def should_auto_start() -> bool:
        """检查是否应该自动启动调度器"""
        from config.settings import get_notification_settings
        settings = get_notification_settings()
        return settings["enabled"] and bool(settings["webhook_url"])


def start_notification_scheduler(experiments: List[Dict[str, Any]], 
                               parse_date_func: Callable = None,
                               is_workday_func: Callable = None,
                               get_holiday_info_func: Callable = None):
    """启动通知调度器（保持向后兼容）"""
    return SchedulerManager.safe_start_scheduler(experiments, parse_date_func, is_workday_func, get_holiday_info_func)


def stop_notification_scheduler():
    """停止通知调度器"""
    return SchedulerManager.safe_stop_scheduler()


def is_scheduler_running():
    """检查调度器是否在运行"""
    return SchedulerManager.get_scheduler_status()


def update_scheduler_experiments(experiments: List[Dict[str, Any]]):
    """更新调度器中的实验数据"""
    _scheduler.update_experiments(experiments)


def send_manual_notification(notification_type: str = "daily"):
    """手动发送今日实验内容"""
    return _scheduler.send_manual_notification(notification_type)


def force_reset_scheduler():
    """强制重置调度器状态"""
    return _scheduler.force_reset()


def restore_scheduler_state():
    """从配置文件恢复调度器状态"""
    # 使用调度器管理器检查是否应该自动启动
    return SchedulerManager.should_auto_start()
