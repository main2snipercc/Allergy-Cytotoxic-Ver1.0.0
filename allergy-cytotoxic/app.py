import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import json
import os
from pathlib import Path
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 导入自定义模块
from config.settings import (
    get_cytotoxic_methods, get_method_steps, get_notification_settings, 
    update_notification_settings, validate_webhook_url, validate_time_format
)
from utils.calendar_utils import (
    get_month_calendar, get_week_calendar, is_workday, get_holiday_info,
    format_date_for_display
)
from utils.schedule_utils import ExperimentScheduler
from utils.scheduler import (
    start_notification_scheduler, stop_notification_scheduler, 
    is_scheduler_running, send_manual_notification
)
from utils.notification import test_notification

# 页面配置
st.set_page_config(
    page_title="细胞毒实验排班系统",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 数据目录
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

# 实验数据文件
EXPERIMENTS_FILE = DATA_DIR / "experiments.json"

# 初始化会话状态
if 'experiments' not in st.session_state:
    st.session_state.experiments = []

if 'scheduler_started' not in st.session_state:
    st.session_state.scheduler_started = False

# 初始化调度器
scheduler = ExperimentScheduler()

def load_experiments():
    """加载实验数据"""
    if EXPERIMENTS_FILE.exists():
        try:
            with open(EXPERIMENTS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 转换日期字符串为date对象
                for exp in data:
                    exp['start_date'] = datetime.strptime(exp['start_date'], '%Y-%m-%d').date()
                    exp['end_date'] = datetime.strptime(exp['end_date'], '%Y-%m-%d').date()
                    for step in exp['steps']:
                        step['scheduled_date'] = datetime.strptime(step['scheduled_date'], '%Y-%m-%d').date()
                return data
        except Exception as e:
            st.error(f"加载实验数据失败: {e}")
    return []

def save_experiments(experiments):
    """保存实验数据"""
    try:
        # 转换date对象为字符串
        data_to_save = []
        for exp in experiments:
            exp_copy = exp.copy()
            exp_copy['start_date'] = exp['start_date'].strftime('%Y-%m-%d')
            exp_copy['end_date'] = exp['end_date'].strftime('%Y-%m-%d')
            exp_copy['steps'] = []
            for step in exp['steps']:
                step_copy = step.copy()
                step_copy['scheduled_date'] = step['scheduled_date'].strftime('%Y-%m-%d')
                exp_copy['steps'].append(step_copy)
            data_to_save.append(exp_copy)
        
        with open(EXPERIMENTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        st.error(f"保存实验数据失败: {e}")
        return False

def add_experiment(start_date, method_name, sample_batch, notes):
    """添加新实验"""
    try:
        experiment = scheduler.calculate_experiment_schedule(
            start_date, method_name, sample_batch, notes
        )
        st.session_state.experiments.append(experiment)
        save_experiments(st.session_state.experiments)
        
        # 更新调度器数据
        if st.session_state.scheduler_started:
            from utils.scheduler import update_scheduler_experiments
            update_scheduler_experiments(st.session_state.experiments)
        
        st.success(f"实验 '{sample_batch}' 已添加成功！")
        return True
    except Exception as e:
        st.error(f"添加实验失败: {e}")
        return False

def delete_experiment(index):
    """删除实验"""
    if 0 <= index < len(st.session_state.experiments):
        deleted_exp = st.session_state.experiments.pop(index)
        save_experiments(st.session_state.experiments)
        
        # 更新调度器数据
        if st.session_state.scheduler_started:
            from utils.scheduler import update_scheduler_experiments
            update_scheduler_experiments(st.session_state.experiments)
        
        st.success(f"实验 '{deleted_exp['sample_batch']}' 已删除！")
        return True
    return False

def render_calendar_view(year, month):
    """渲染日历视图"""
    calendar_data = get_month_calendar(year, month)
    
    # 创建日历表格
    st.subheader(f"{year}年{month}月日历")
    
    # 获取每日实验安排
    daily_schedule = scheduler.create_daily_schedule(st.session_state.experiments)
    
    # 创建日历网格
    col_names = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
    
    # 使用列布局创建日历
    cols = st.columns(7)
    
    # 显示星期标题
    for i, col in enumerate(cols):
        col.markdown(f"**{col_names[i]}**")
    
    # 显示日历内容
    for week in calendar_data:
        cols = st.columns(7)
        for i, day_data in enumerate(week):
            col = cols[i]
            
            # 日期样式
            date_style = ""
            if day_data['is_today']:
                date_style = "🔴"
            elif not day_data['is_current_month']:
                date_style = "⚪"
            elif not day_data['is_workday']:
                date_style = "🔵"
            else:
                date_style = "⚫"
            
            # 显示日期
            col.markdown(f"{date_style} {day_data['day']}")
            
            # 显示实验安排
            date_key = day_data['date'].strftime('%Y-%m-%d')
            if date_key in daily_schedule:
                tasks = daily_schedule[date_key]
                for task in tasks[:3]:  # 最多显示3个任务
                    col.markdown(f"• {task['step_name']}")
                if len(tasks) > 3:
                    col.markdown(f"...还有{len(tasks)-3}个")

def render_weekly_view(target_date=None):
    """渲染周视图"""
    if target_date is None:
        target_date = date.today()
    
    week_data = get_week_calendar(target_date)
    daily_schedule = scheduler.create_daily_schedule(st.session_state.experiments)
    
    st.subheader(f"周视图 ({target_date.strftime('%Y年%m月%d日')}所在周)")
    
    # 创建周视图表格
    week_df = pd.DataFrame(week_data)
    
    # 添加实验安排列
    week_df['实验安排'] = week_df['date'].apply(
        lambda x: daily_schedule.get(x.strftime('%Y-%m-%d'), [])
    )
    
    # 显示周视图
    for i, row in week_df.iterrows():
        col1, col2, col3 = st.columns([1, 2, 3])
        
        with col1:
            date_obj = row['date']
            if row['is_today']:
                st.markdown(f"**🔴 {row['weekday']} ({date_obj.strftime('%m/%d')})**")
            else:
                st.markdown(f"**{row['weekday']} ({date_obj.strftime('%m/%d')})**")
        
        with col2:
            if row['is_workday']:
                st.markdown("✅ 工作日")
            else:
                st.markdown("❌ 非工作日")
            
            if row['holiday_name']:
                st.markdown(f"🎉 {row['holiday_name']}")
        
        with col3:
            tasks = row['实验安排']
            if tasks:
                for task in tasks:
                    st.markdown(f"• **{task['sample_batch']}**: {task['step_name']}")
            else:
                st.markdown("无实验安排")

def render_daily_summary():
    """渲染每日汇总表格"""
    if not st.session_state.experiments:
        st.info("暂无实验数据")
        return
    
    daily_schedule = scheduler.create_daily_schedule(st.session_state.experiments)
    
    # 转换为DataFrame
    daily_data = []
    for date_key, tasks in daily_schedule.items():
        for task in tasks:
            daily_data.append({
                '日期': date_key,
                '样品批号': task['sample_batch'],
                '检测方法': task['method_name'],
                '实验内容': task['step_name'],
                '备注': task['notes']
            })
    
    if daily_data:
        df = pd.DataFrame(daily_data)
        df = df.sort_values('日期')
        
        st.subheader("每日实验汇总")
        st.dataframe(df, use_container_width=True)
        
        # 导出功能
        col1, col2 = st.columns(2)
        with col1:
            if st.button("导出到Excel"):
                filename = scheduler.export_schedule_to_excel(st.session_state.experiments)
                st.success(f"已导出到: {filename}")
        
        with col2:
            if st.button("下载CSV"):
                csv = df.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(
                    label="下载CSV文件",
                    data=csv,
                    file_name=f"实验排班表_{date.today().strftime('%Y%m%d')}.csv",
                    mime="text/csv"
                )
    else:
        st.info("暂无实验安排")

def render_experiment_form():
    """渲染实验添加表单"""
    st.subheader("添加新实验")
    
    with st.form("experiment_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            start_date = st.date_input(
                "上样日期",
                value=date.today(),
                format="YYYY-MM-DD"
            )
            
            sample_batch = st.text_input("样品批号", placeholder="请输入样品批号")
        
        with col2:
            methods = list(get_cytotoxic_methods().keys())
            method_name = st.selectbox("检测方法", methods)
            
            notes = st.text_area("备注", placeholder="请输入备注信息")
        
        submitted = st.form_submit_button("添加实验")
        
        if submitted:
            if not sample_batch.strip():
                st.error("请输入样品批号")
                return
            
            # 验证数据
            is_valid, message = scheduler.validate_experiment_data(
                start_date.strftime('%Y-%m-%d'), method_name, sample_batch
            )
            
            if not is_valid:
                st.error(message)
                return
            
            # 添加实验
            if add_experiment(start_date.strftime('%Y-%m-%d'), method_name, sample_batch, notes):
                st.rerun()

def render_experiment_list():
    """渲染实验列表"""
    if not st.session_state.experiments:
        st.info("暂无实验数据")
        return
    
    st.subheader("实验列表")
    
    for i, exp in enumerate(st.session_state.experiments):
        with st.expander(f"{exp['sample_batch']} - {exp['method_name']} ({exp['start_date']})"):
            col1, col2, col3 = st.columns([3, 1, 1])
            
            with col1:
                st.markdown(f"**样品批号**: {exp['sample_batch']}")
                st.markdown(f"**检测方法**: {exp['method_name']}")
                st.markdown(f"**开始日期**: {exp['start_date']}")
                st.markdown(f"**结束日期**: {exp['end_date']}")
                st.markdown(f"**备注**: {exp['notes']}")
            
            with col2:
                st.markdown("**实验步骤:**")
                for step in exp['steps']:
                    st.markdown(f"• 第{step['relative_day']}天: {step['step_name']}")
                    st.markdown(f"  ({step['scheduled_date']})")
            
            with col3:
                if st.button(f"删除", key=f"delete_{i}"):
                    delete_experiment(i)
                    st.rerun()

def render_notification_settings():
    """渲染通知设置"""
    st.subheader("通知设置")
    
    settings = get_notification_settings()
    
    with st.form("notification_settings"):
        enabled = st.checkbox("启用通知", value=settings["enabled"])
        
        webhook_url = st.text_input(
            "企业微信Webhook地址",
            value=settings["webhook_url"],
            placeholder="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=..."
        )
        
        push_time = st.time_input(
            "每日推送时间",
            value=datetime.strptime(settings["push_time"], "%H:%M").time()
        )
        
        reminder_days = st.multiselect(
            "提前提醒天数",
            options=[1, 2, 3, 5, 7],
            default=settings["reminder_days"]
        )
        
        col1, col2 = st.columns(2)
        
        with col1:
            submitted = st.form_submit_button("保存设置")
            if submitted:
                # 验证webhook地址
                is_valid, message = validate_webhook_url(webhook_url)
                if not is_valid:
                    st.error(message)
                    return
                
                # 保存设置
                success = update_notification_settings(
                    enabled=enabled,
                    webhook_url=webhook_url,
                    push_time=push_time.strftime("%H:%M"),
                    reminder_days=reminder_days
                )
                
                if success:
                    st.success("设置已保存")
                else:
                    st.error("保存设置失败")
        
        with col2:
            if st.button("测试连接"):
                success, message = test_notification()
                if success:
                    st.success(message)
                else:
                    st.error(message)
    
    # 调度器控制
    st.markdown("---")
    st.markdown("**调度器控制**")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("启动调度器"):
            if not st.session_state.scheduler_started:
                start_notification_scheduler(st.session_state.experiments)
                st.session_state.scheduler_started = True
                st.success("调度器已启动")
            else:
                st.info("调度器已在运行中")
    
    with col2:
        if st.button("停止调度器"):
            if st.session_state.scheduler_started:
                stop_notification_scheduler()
                st.session_state.scheduler_started = False
                st.success("调度器已停止")
            else:
                st.info("调度器未在运行")
    
    with col3:
        if st.button("手动发送通知"):
            if st.session_state.experiments:
                success = send_manual_notification("daily")
                if success:
                    st.success("通知发送成功")
                else:
                    st.error("通知发送失败")
            else:
                st.warning("暂无实验数据可发送")
    
    # 显示调度器状态
    status = "运行中" if st.session_state.scheduler_started else "已停止"
    st.info(f"调度器状态: {status}")

def main():
    """主函数"""
    st.title("🧪 细胞毒实验排班系统")
    st.markdown("---")
    
    # 加载实验数据
    if not st.session_state.experiments:
        st.session_state.experiments = load_experiments()
    
    # 侧边栏
    with st.sidebar:
        st.header("导航")
        page = st.selectbox(
            "选择页面",
            ["实验管理", "日历视图", "周视图", "每日汇总", "通知设置", "系统信息"]
        )
        
        st.markdown("---")
        st.markdown("**快速统计**")
        st.metric("实验总数", len(st.session_state.experiments))
        
        if st.session_state.experiments:
            total_steps = sum(len(exp['steps']) for exp in st.session_state.experiments)
            st.metric("总步骤数", total_steps)
            
            # 计算即将到来的实验
            upcoming = scheduler.get_upcoming_experiments(st.session_state.experiments, 7)
            st.metric("7天内实验", len(upcoming))
    
    # 主内容区域
    if page == "实验管理":
        col1, col2 = st.columns([1, 1])
        
        with col1:
            render_experiment_form()
        
        with col2:
            render_experiment_list()
    
    elif page == "日历视图":
        col1, col2 = st.columns([1, 3])
        
        with col1:
            current_date = date.today()
            year = st.number_input("年份", value=current_date.year, min_value=2020, max_value=2030)
            month = st.number_input("月份", value=current_date.month, min_value=1, max_value=12)
        
        with col2:
            render_calendar_view(year, month)
    
    elif page == "周视图":
        col1, col2 = st.columns([1, 3])
        
        with col1:
            target_date = st.date_input(
                "选择日期",
                value=date.today(),
                format="YYYY-MM-DD"
            )
        
        with col2:
            render_weekly_view(target_date)
    
    elif page == "每日汇总":
        render_daily_summary()
    
    elif page == "通知设置":
        render_notification_settings()
    
    elif page == "系统信息":
        st.subheader("系统信息")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**检测方法信息**")
            method_summary = scheduler.get_method_summary()
            for method in method_summary:
                with st.expander(f"{method['方法名称']}"):
                    st.markdown(f"**总天数**: {method['总天数']}")
                    st.markdown(f"**步骤数**: {method['步骤数']}")
                    st.markdown("**步骤描述**:")
                    for step in method['步骤描述']:
                        st.markdown(f"• {step}")
        
        with col2:
            st.markdown("**系统状态**")
            st.info(f"Python版本: {st.get_option('server.enableCORS')}")
            st.info(f"Streamlit版本: {st.__version__}")
            st.info(f"数据文件: {EXPERIMENTS_FILE}")
            st.info(f"调度器状态: {'运行中' if st.session_state.scheduler_started else '已停止'}")

if __name__ == "__main__":
    main()
