from datetime import datetime, date, timedelta
from typing import List, Dict, Any
from config.settings import get_cytotoxic_methods, get_method_steps
from utils.calendar_utils import is_workday, get_next_workday


class ExperimentScheduler:
    """实验排班调度器"""
    
    def __init__(self):
        self.methods = get_cytotoxic_methods()
    
    def calculate_experiment_schedule(self, start_date: str, method_name: str, 
                                    sample_batch: str = "", notes: str = "") -> Dict[str, Any]:
        """
        计算实验排班
        
        Args:
            start_date: 上样日期 (YYYY-MM-DD)
            method_name: 检测方法名称
            sample_batch: 样品批号
            notes: 备注
        
        Returns:
            包含实验排班信息的字典
        """
        if method_name not in self.methods:
            raise ValueError(f"不支持的检测方法: {method_name}")
        
        # 解析开始日期
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        
        method_info = self.methods[method_name]
        steps = method_info["steps"]
        
        # 计算每个步骤的日期
        schedule_steps = []
        for step in steps:
            step_date = start_date + timedelta(days=step["day"] - 1)
            
            # 如果步骤日期是周末或节假日，调整到下一个工作日
            if not is_workday(step_date):
                step_date = get_next_workday(step_date)
            
            schedule_steps.append({
                "step_name": step["action"],
                "description": step["description"],
                "relative_day": step["day"],
                "scheduled_date": step_date,
                "is_workday": is_workday(step_date),
                "date_str": step_date.strftime("%Y-%m-%d")
            })
        
        # 计算实验结束日期
        end_date = max(step["scheduled_date"] for step in schedule_steps)
        
        return {
            "method_name": method_name,
            "start_date": start_date,
            "end_date": end_date,
            "sample_batch": sample_batch,
            "notes": notes,
            "steps": schedule_steps,
            "total_days": (end_date - start_date).days + 1
        }
    
    def create_daily_schedule(self, experiments: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        创建每日实验安排汇总
        
        Args:
            experiments: 实验列表
        
        Returns:
            按日期分组的实验安排
        """
        daily_schedule = {}
        
        for exp in experiments:
            for step in exp["steps"]:
                date_key = step["date_str"]
                
                if date_key not in daily_schedule:
                    daily_schedule[date_key] = []
                
                daily_schedule[date_key].append({
                    "sample_batch": exp["sample_batch"],
                    "method_name": exp["method_name"],
                    "step_name": step["step_name"],
                    "description": step["description"],
                    "relative_day": step["relative_day"],
                    "notes": exp["notes"],
                    "start_date": exp["start_date"].strftime("%Y-%m-%d")
                })
        
        return daily_schedule
    
    def get_upcoming_experiments(self, experiments: List[Dict[str, Any]], 
                                days_ahead: int = 7) -> List[Dict[str, Any]]:
        """
        获取即将到来的实验安排
        
        Args:
            experiments: 实验列表
            days_ahead: 提前天数
        
        Returns:
            即将到来的实验列表
        """
        today = date.today()
        target_date = today + timedelta(days=days_ahead)
        
        upcoming = []
        for exp in experiments:
            for step in exp["steps"]:
                if step["scheduled_date"] <= target_date and step["scheduled_date"] >= today:
                    upcoming.append({
                        "sample_batch": exp["sample_batch"],
                        "method_name": exp["method_name"],
                        "step_name": step["step_name"],
                        "description": step["description"],
                        "scheduled_date": step["scheduled_date"],
                        "days_until": (step["scheduled_date"] - today).days,
                        "notes": exp["notes"]
                    })
        
        # 按日期排序
        upcoming.sort(key=lambda x: x["scheduled_date"])
        return upcoming
    
    def export_schedule_to_excel(self, experiments: List[Dict[str, Any]], 
                                filename: str = "实验排班表.xlsx"):
        """
        导出排班表到Excel文件
        
        Args:
            experiments: 实验列表
            filename: 文件名
        """
        import pandas as pd
        
        # 创建详细步骤表
        detailed_data = []
        for exp in experiments:
            for step in exp["steps"]:
                detailed_data.append({
                    "样品批号": exp["sample_batch"],
                    "检测方法": exp["method_name"],
                    "步骤名称": step["step_name"],
                    "步骤描述": step["description"],
                    "相对天数": step["relative_day"],
                    "计划日期": step["scheduled_date"],
                    "是否工作日": "是" if step["is_workday"] else "否",
                    "备注": exp["notes"]
                })
        
        # 创建每日汇总表
        daily_schedule = self.create_daily_schedule(experiments)
        daily_data = []
        
        for date_key, tasks in daily_schedule.items():
            for task in tasks:
                daily_data.append({
                    "日期": date_key,
                    "样品批号": task["sample_batch"],
                    "检测方法": task["method_name"],
                    "实验内容": task["step_name"],
                    "备注": task["notes"]
                })
        
        # 创建Excel文件
        with pd.ExcelWriter(filename, engine='openpyxl') as writer:
            pd.DataFrame(detailed_data).to_excel(writer, sheet_name='详细步骤', index=False)
            pd.DataFrame(daily_data).to_excel(writer, sheet_name='每日汇总', index=False)
        
        return filename
    
    def validate_experiment_data(self, start_date: str, method_name: str, 
                                sample_batch: str) -> tuple[bool, str]:
        """
        验证实验数据
        
        Args:
            start_date: 开始日期
            method_name: 方法名称
            sample_batch: 样品批号
        
        Returns:
            (是否有效, 错误信息)
        """
        # 验证日期格式
        try:
            datetime.strptime(start_date, "%Y-%m-%d")
        except ValueError:
            return False, "日期格式错误，请使用YYYY-MM-DD格式"
        
        # 验证方法名称
        if method_name not in self.methods:
            return False, f"不支持的检测方法: {method_name}"
        
        # 验证样品批号
        if not sample_batch.strip():
            return False, "样品批号不能为空"
        
        return True, "数据验证通过"
    
    def get_method_summary(self) -> List[Dict[str, Any]]:
        """
        获取所有检测方法的摘要信息
        
        Returns:
            方法摘要列表
        """
        summary = []
        for method_name, method_info in self.methods.items():
            steps = method_info["steps"]
            total_days = max(step["day"] for step in steps)
            
            summary.append({
                "方法名称": method_name,
                "总天数": total_days,
                "步骤数": len(steps),
                "步骤描述": [step["description"] for step in steps]
            })
        
        return summary
