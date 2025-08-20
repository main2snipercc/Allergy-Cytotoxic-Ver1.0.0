import chinese_calendar
from datetime import datetime, date, timedelta
import calendar as cal


def is_workday(check_date):
    """判断是否为工作日（排除周末和节假日）"""
    if isinstance(check_date, str):
        check_date = datetime.strptime(check_date, "%Y-%m-%d").date()
    elif isinstance(check_date, datetime):
        check_date = check_date.date()
    
    # 使用chinese_calendar判断是否为工作日
    return chinese_calendar.is_workday(check_date)


def get_holiday_info(check_date):
    """获取节假日信息"""
    if isinstance(check_date, str):
        check_date = datetime.strptime(check_date, "%Y-%m-%d").date()
    elif isinstance(check_date, datetime):
        check_date = check_date.date()
    
    try:
        # 获取节假日名称
        holiday_name = chinese_calendar.get_holiday_detail(check_date)[1]
        return holiday_name if holiday_name else None
    except:
        return None


def get_month_calendar(year, month):
    """获取指定年月的日历数据"""
    # 获取月份第一天和最后一天
    first_day = date(year, month, 1)
    last_day = date(year, month, cal.monthrange(year, month)[1])
    
    # 获取月份第一天是周几（0=周一，6=周日）
    first_weekday = first_day.weekday()
    
    # 计算需要显示的前一个月末尾的日期
    prev_month_end = first_day - timedelta(days=first_weekday + 1)
    
    calendar_data = []
    current_date = prev_month_end
    
    # 生成6周的日历数据
    for week in range(6):
        week_data = []
        for day in range(7):
            current_date += timedelta(days=1)
            
            # 判断日期属性
            is_current_month = current_date.month == month
            is_today = current_date == date.today()
            is_work = is_workday(current_date)
            holiday_info = get_holiday_info(current_date)
            
            week_data.append({
                'date': current_date,
                'day': current_date.day,
                'is_current_month': is_current_month,
                'is_today': is_today,
                'is_workday': is_work,
                'holiday_name': holiday_info,
                'is_weekend': current_date.weekday() >= 5
            })
        calendar_data.append(week_data)
    
    return calendar_data


def get_week_calendar(target_date=None):
    """获取指定日期所在周的日历数据"""
    if target_date is None:
        target_date = date.today()
    elif isinstance(target_date, str):
        target_date = datetime.strptime(target_date, "%Y-%m-%d").date()
    elif isinstance(target_date, datetime):
        target_date = target_date.date()
    
    # 计算本周一
    monday = target_date - timedelta(days=target_date.weekday())
    
    week_data = []
    for i in range(7):
        current_date = monday + timedelta(days=i)
        is_work = is_workday(current_date)
        holiday_info = get_holiday_info(current_date)
        
        week_data.append({
            'date': current_date,
            'day': current_date.day,
            'is_today': current_date == date.today(),
            'is_workday': is_work,
            'holiday_name': holiday_info,
            'is_weekend': current_date.weekday() >= 5,
            'weekday': ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][i]
        })
    
    return week_data


def get_date_range(start_date, end_date):
    """获取日期范围内的所有日期"""
    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
    if isinstance(end_date, str):
        end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
    
    date_list = []
    current_date = start_date
    
    while current_date <= end_date:
        is_work = is_workday(current_date)
        holiday_info = get_holiday_info(current_date)
        
        date_list.append({
            'date': current_date,
            'day': current_date.day,
            'is_workday': is_work,
            'holiday_name': holiday_info,
            'is_weekend': current_date.weekday() >= 5
        })
        
        current_date += timedelta(days=1)
    
    return date_list


def format_date_for_display(date_obj):
    """格式化日期显示"""
    if isinstance(date_obj, str):
        date_obj = datetime.strptime(date_obj, "%Y-%m-%d").date()
    elif isinstance(date_obj, datetime):
        date_obj = date_obj.date()
    
    return date_obj.strftime("%Y年%m月%d日")


def get_next_workday(check_date):
    """获取下一个工作日"""
    if isinstance(check_date, str):
        check_date = datetime.strptime(check_date, "%Y-%m-%d").date()
    elif isinstance(check_date, datetime):
        check_date = check_date.date()
    
    next_date = check_date + timedelta(days=1)
    while not is_workday(next_date):
        next_date += timedelta(days=1)
    
    return next_date


def get_previous_workday(check_date):
    """获取上一个工作日"""
    if isinstance(check_date, str):
        check_date = datetime.strptime(check_date, "%Y-%m-%d").date()
    elif isinstance(check_date, datetime):
        check_date = check_date.date()
    
    prev_date = check_date - timedelta(days=1)
    while not is_workday(prev_date):
        prev_date -= timedelta(days=1)
    
    return prev_date
