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
from utils.data_archive import auto_archive_experiments, get_archive_statistics, manual_archive_by_exp_id, manual_archive_by_sample_batch

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

# 初始化编辑状态
if 'editing_index' not in st.session_state:
    st.session_state.editing_index = None

if 'editing_experiment' not in st.session_state:
    st.session_state.editing_experiment = None

# 初始化查询状态
if 'query_executed' not in st.session_state:
    st.session_state.query_executed = False

# 初始化Webhook编辑状态
if 'editing_webhook' not in st.session_state:
    st.session_state.editing_webhook = False

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
                
                # 自动归档过期数据
                if data:
                    archived_count = 0
                    try:
                        data, archived_count = auto_archive_experiments(data, archive_threshold_days=180)
                        if archived_count > 0:
                            # 保存归档后的数据
                            save_experiments(data)
                            print(f"自动归档了 {archived_count} 个过期实验")
                    except Exception as e:
                        print(f"自动归档失败: {e}")
                
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

def add_experiment(start_date, method_name, sample_batch, notes, manual_exp_id=None, allow_duplicate_exp_id=False):
    """添加新实验"""
    try:
        # 处理实验序号
        if manual_exp_id is not None:
            # 验证手动指定的实验序号
            is_valid, message = scheduler.validate_exp_id(manual_exp_id, st.session_state.experiments, allow_duplicate_exp_id)
            if not is_valid:
                st.error(f"实验序号验证失败: {message}")
                return False
            exp_id = manual_exp_id
        else:
            # 自动生成实验序号（从1开始递增）
            if st.session_state.experiments:
                max_exp_id = max(exp.get('exp_id', 0) for exp in st.session_state.experiments)
                exp_id = max_exp_id + 1
            else:
                exp_id = 1
        
        experiment = scheduler.calculate_experiment_schedule(
            start_date, method_name, sample_batch, notes
        )
        
        # 添加实验序号
        experiment['exp_id'] = exp_id
        
        st.session_state.experiments.append(experiment)
        save_experiments(st.session_state.experiments)
        
        # 更新调度器数据
        if st.session_state.scheduler_started:
            from utils.scheduler import update_scheduler_experiments
            update_scheduler_experiments(st.session_state.experiments)
        
        st.success(f"实验 #{exp_id} '{sample_batch}' 已添加成功！")
        return True
    except Exception as e:
        st.error(f"添加实验失败: {e}")
        return False

def delete_experiment(index):
    """删除单个实验"""
    if 0 <= index < len(st.session_state.experiments):
        deleted_exp = st.session_state.experiments.pop(index)
        save_experiments(st.session_state.experiments)
        
        # 更新调度器数据
        if st.session_state.scheduler_started:
            from utils.scheduler import update_scheduler_experiments
            update_scheduler_experiments(st.session_state.experiments)
        
        # 记录删除信息但不显示成功消息（批量删除时由调用方处理）
        return True
    return False

def delete_experiments_by_exp_id(exp_id):
    """根据实验序号删除所有相关实验"""
    if not st.session_state.experiments:
        return 0
    
    # 找到所有匹配的实验序号
    indices_to_delete = []
    for i, exp in enumerate(st.session_state.experiments):
        if exp.get('exp_id') == exp_id:
            indices_to_delete.append(i)
    
    # 按索引倒序删除（避免索引变化问题）
    deleted_count = 0
    for index in sorted(indices_to_delete, reverse=True):
        if delete_experiment(index):
            deleted_count += 1
    
    return deleted_count

def edit_experiment(index):
    """编辑实验"""
    if 0 <= index < len(st.session_state.experiments):
        # 设置编辑状态
        st.session_state.editing_index = index
        st.session_state.editing_experiment = st.session_state.experiments[index].copy()
        return True
    return False

def update_experiment(index, start_date, method_name, sample_batch, notes):
    """更新实验信息"""
    if 0 <= index < len(st.session_state.experiments):
        try:
            # 保存原有的实验序号
            original_exp_id = st.session_state.experiments[index]['exp_id']
            
            # 创建新的实验数据
            updated_experiment = scheduler.calculate_experiment_schedule(
                start_date, method_name, sample_batch, notes
            )
            
            # 保持原有的实验序号
            updated_experiment['exp_id'] = original_exp_id
            
            # 更新实验
            st.session_state.experiments[index] = updated_experiment
            save_experiments(st.session_state.experiments)
            
            # 更新调度器数据
            if st.session_state.scheduler_started:
                from utils.scheduler import update_scheduler_experiments
                update_scheduler_experiments(st.session_state.experiments)
            
            # 清除编辑状态
            st.session_state.editing_index = None
            st.session_state.editing_experiment = None
            
            st.success(f"实验 #{updated_experiment['exp_id']} '{sample_batch}' 已更新成功！")
            return True
        except Exception as e:
            st.error(f"更新实验失败: {e}")
            return False
    return False

def render_calendar_view(year, month):
    """渲染日历视图"""
    calendar_data = get_month_calendar(year, month)
    
    # 创建日历表格
    st.subheader(f"{year}年{month}月日历")
    
    # 添加图例说明
    st.markdown("**图例说明：**")
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.markdown("🔴 **今天**")
    with col2:
        st.markdown("🟢 **工作日**")
    with col3:
        st.markdown("🔵 **非工作日**")
    with col4:
        st.markdown("⚪ **非本月**")
    with col5:
        st.markdown("📋 **有实验安排**")
    
    st.markdown("---")
    
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
            
            # 创建日期容器
            with col.container():
                # 日期样式 - 使用更清晰的图标和颜色
                if day_data['is_today']:
                    date_style = "🔴"
                    date_class = "今天"
                    # 使用特殊样式突出今天
                    st.markdown(f"""
                    <div style="
                        background-color: #ffebee; 
                        border: 2px solid #f44336; 
                        border-radius: 8px; 
                        padding: 8px; 
                        margin: 2px;
                        text-align: center;
                    ">
                        <h3 style="margin: 0; color: #d32f2f;">{day_data['day']}</h3>
                        <p style="margin: 2px 0; font-size: 12px; color: #d32f2f;">{date_class}</p>
                    </div>
                    """, unsafe_allow_html=True)
                elif not day_data['is_current_month']:
                    date_style = "⚪"
                    date_class = "非本月"
                    st.markdown(f"""
                    <div style="
                        background-color: #f5f5f5; 
                        border: 1px solid #e0e0e0; 
                        border-radius: 6px; 
                        padding: 6px; 
                        margin: 2px;
                        text-align: center;
                        opacity: 0.5;
                    ">
                        <h4 style="margin: 0; color: #9e9e9e;">{day_data['day']}</h4>
                        <p style="margin: 2px 0; font-size: 10px; color: #9e9e9e;">{date_class}</p>
                    </div>
                    """, unsafe_allow_html=True)
                elif not day_data['is_workday']:
                    date_style = "🔵"
                    date_class = "非工作日"
                    st.markdown(f"""
                    <div style="
                        background-color: #e3f2fd; 
                        border: 1px solid #2196f3; 
                        border-radius: 6px; 
                        padding: 6px; 
                        margin: 2px;
                        text-align: center;
                    ">
                        <h4 style="margin: 0; color: #1976d2;">{day_data['day']}</h4>
                        <p style="margin: 2px 0; font-size: 10px; color: #1976d2;">{date_class}</p>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    date_style = "🟢"
                    date_class = "工作日"
                    st.markdown(f"""
                    <div style="
                        background-color: #e8f5e8; 
                        border: 1px solid #4caf50; 
                        border-radius: 6px; 
                        padding: 6px; 
                        margin: 2px;
                        text-align: center;
                    ">
                        <h4 style="margin: 0; color: #388e3c;">{day_data['day']}</h4>
                        <p style="margin: 2px 0; font-size: 10px; color: #388e3c;">{date_class}</p>
                    </div>
                    """, unsafe_allow_html=True)
                
                # 显示节假日信息
                if day_data['holiday_name']:
                    st.markdown(f"🎉 **{day_data['holiday_name']}**")
                
                # 显示实验安排 - 按实验序号聚合显示
                date_key = day_data['date'].strftime('%Y-%m-%d')
                if date_key in daily_schedule:
                    tasks = daily_schedule[date_key]
                    
                    # 按实验序号聚合
                    exp_groups = {}
                    for task in tasks:
                        exp_id = task['exp_id']
                        if exp_id not in exp_groups:
                            exp_groups[exp_id] = []
                        exp_groups[exp_id].append(task)
                    
                    if len(exp_groups) == 1:
                        # 只有一个实验序号时
                        exp_id = list(exp_groups.keys())[0]
                        tasks_for_exp = exp_groups[exp_id]
                        st.markdown("📋 **实验安排：**")
                        st.markdown(f"• 实验#{exp_id}: {tasks_for_exp[0]['step_name']}")
                        if len(tasks_for_exp) > 1:
                            st.markdown(f"  ({len(tasks_for_exp)}个样品)")
                    else:
                        # 多个实验序号时使用折叠卡片
                        exp_ids = list(exp_groups.keys())
                        exp_ids_str = ", ".join([f"#{exp_id}" for exp_id in exp_ids])
                        
                        with st.expander(f"📋 **实验安排：{len(exp_groups)}个实验序号** ({exp_ids_str})", expanded=False):
                            for exp_id, tasks_for_exp in exp_groups.items():
                                st.markdown(f"**实验#{exp_id}**: {tasks_for_exp[0]['step_name']}")
                                if len(tasks_for_exp) > 1:
                                    st.markdown(f"  📦 {len(tasks_for_exp)}个样品")
                                
                                # 显示该实验序号下的所有步骤
                                step_names = list(set([task['step_name'] for task in tasks_for_exp]))
                                if len(step_names) > 1:
                                    st.markdown(f"  📋 步骤: {', '.join(step_names)}")
                                
                                st.markdown("---")
                else:
                    st.markdown("📅 无安排")

def render_weekly_view(target_date=None):
    """渲染周视图"""
    if target_date is None:
        target_date = date.today()
    
    week_data = get_week_calendar(target_date)
    daily_schedule = scheduler.create_daily_schedule(st.session_state.experiments)
    
    st.subheader(f"周视图 ({target_date.strftime('%Y年%m月%d日')}所在周)")
    
    # 添加图例说明
    st.markdown("**图例说明：**")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown("🔴 **今天**")
    with col2:
        st.markdown("🟢 **工作日**")
    with col3:
        st.markdown("🔵 **非工作日**")
    with col4:
        st.markdown("📋 **有实验安排**")
    
    st.markdown("---")
    
    # 创建周视图表格
    week_df = pd.DataFrame(week_data)
    
    # 添加实验安排列
    week_df['实验安排'] = week_df['date'].apply(
        lambda x: daily_schedule.get(x.strftime('%Y-%m-%d'), [])
    )
    
    # 显示周视图 - 使用Streamlit原生组件
    for i, row in week_df.iterrows():
        # 使用容器来组织内容
        with st.container():
            # 根据日期类型设置不同的状态
            if row['is_today']:
                status_icon = "🔴"
                status_text = "今天"
                border_color = "red"
            elif row['is_workday']:
                status_icon = "🟢"
                status_text = "工作日"
                border_color = "green"
            else:
                status_icon = "🔵"
                status_text = "非工作日"
                border_color = "blue"
            
            # 创建带边框的容器
            with st.container(border=True):
                # 创建两列布局
                col1, col2 = st.columns([1, 2])
                
                with col1:
                    # 显示日期信息
                    st.markdown(f"### {row['weekday']} ({row['date'].strftime('%m/%d')})")
                    st.markdown(f"{status_icon} **{status_text}**")
                    
                    # 显示节假日信息
                    if row['holiday_name']:
                        st.markdown(f"🎉 **{row['holiday_name']}**")
                
                with col2:
                    # 显示实验安排 - 按实验序号聚合显示
                    if row['实验安排']:
                        tasks = row['实验安排']
                        
                        # 按实验序号聚合
                        exp_groups = {}
                        for task in tasks:
                            exp_id = task['exp_id']
                            if exp_id not in exp_groups:
                                exp_groups[exp_id] = []
                            exp_groups[exp_id].append(task)
                        
                        if len(exp_groups) == 1:
                            # 只有一个实验序号时
                            exp_id = list(exp_groups.keys())[0]
                            tasks_for_exp = exp_groups[exp_id]
                            st.markdown("**📋 实验安排：**")
                            st.markdown(f"• **实验#{exp_id}**: {tasks_for_exp[0]['step_name']}")
                            if len(tasks_for_exp) > 1:
                                st.markdown(f"  ({len(tasks_for_exp)}个样品)")
                        else:
                            # 多个实验序号时使用折叠卡片
                            exp_ids = list(exp_groups.keys())
                            exp_ids_str = ", ".join([f"#{exp_id}" for exp_id in exp_ids])
                            
                            with st.expander(f"**📋 实验安排：{len(exp_groups)}个实验序号** ({exp_ids_str})", expanded=False):
                                for exp_id, tasks_for_exp in exp_groups.items():
                                    st.markdown(f"**实验#{exp_id}**: {tasks_for_exp[0]['step_name']}")
                                    if len(tasks_for_exp) > 1:
                                        st.markdown(f"  📦 {len(tasks_for_exp)}个样品")
                                    
                                    # 显示该实验序号下的所有步骤
                                    step_names = list(set([task['step_name'] for task in tasks_for_exp]))
                                    if len(step_names) > 1:
                                        st.markdown(f"  📋 步骤: {', '.join(step_names)}")
                                    
                                    st.markdown("---")
                    else:
                        st.markdown("📅 **无实验安排**")

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
                '实验序号': f"#{task['exp_id']}",
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

def render_experiment_query():
    """渲染实验查询页面"""
    st.subheader("🔍 实验查询")
    st.markdown("---")
    
    # 查询条件区域
    with st.container():
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**📅 日期范围查询**")
            date_col1, date_col2 = st.columns(2)
            with date_col1:
                start_date_query = st.date_input(
                    "开始日期", 
                    value=date.today() - timedelta(days=30),
                    format="YYYY-MM-DD"
                )
            with date_col2:
                end_date_query = st.date_input(
                    "结束日期", 
                    value=date.today() + timedelta(days=30),
                    format="YYYY-MM-DD"
                )
        
        with col2:
            st.markdown("**🔬 检测方法查询**")
            method_query = st.selectbox(
                "检测方法", 
                options=["全部"] + list(get_cytotoxic_methods().keys()),
                help="选择特定检测方法或查看全部"
            )
    
    # 高级查询条件
    with st.expander("🔍 高级查询条件", expanded=False):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("**🔢 实验序号查询**")
            exp_id_query = st.number_input(
                "实验序号", 
                min_value=1,
                value=None,
                placeholder="输入实验序号",
                help="输入具体的实验序号进行精确查询，留空则不限制"
            )
        
        with col2:
            st.markdown("**📋 样品批号查询**")
            batch_query = st.text_input(
                "样品批号关键词", 
                placeholder="输入批号关键词，支持模糊查询",
                help="支持部分匹配，如输入'2508'可查询所有包含该数字的批号"
            )
        
        with col3:
            st.markdown("**📝 备注查询**")
            notes_query = st.text_input(
                "备注关键词", 
                placeholder="输入备注关键词",
                help="在备注中搜索包含关键词的实验"
            )
    
    # 实验状态查询
    with st.expander("📊 实验状态筛选", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            status_query = st.selectbox(
                "实验状态", 
                options=["全部", "进行中", "已完成", "即将开始"],
                help="根据实验进度筛选"
            )
        with col2:
            # 归档数据控制
            col2_1, col2_2 = st.columns(2)
            with col2_1:
                include_archived = st.checkbox(
                    "包含归档数据", 
                    value=True,
                    help="是否在查询结果中包含已归档的实验数据"
                )
            with col2_2:
                force_archive_search = st.checkbox(
                    "强制搜索归档数据", 
                    value=False,
                    help="强制搜索归档数据，忽略智能判断条件"
                )
    
    # 查询按钮
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        if st.button("🔍 执行查询", type="primary", use_container_width=True):
            st.session_state.query_executed = True
    
    # 显示查询结果
    if st.session_state.get('query_executed', False):
        st.markdown("---")
        st.subheader("📊 查询结果")
        
        # 执行查询逻辑
        query_results = []
        today = date.today()
        
        # 1. 首先搜索活跃数据
        active_results = []
        for exp in st.session_state.experiments:
            match = True
            
            # 实验序号筛选
            if exp_id_query and exp.get('exp_id') != exp_id_query:
                match = False
            
            # 日期范围筛选
            if exp['start_date'] > end_date_query or exp['end_date'] < start_date_query:
                match = False
            
            # 检测方法筛选
            if method_query != "全部" and exp['method_name'] != method_query:
                match = False
            
            # 样品批号筛选
            if batch_query and batch_query.lower() not in exp['sample_batch'].lower():
                match = False
            
            # 备注筛选
            if notes_query and notes_query.lower() not in exp['notes'].lower():
                match = False
            
            # 实验状态筛选
            if status_query != "全部":
                if status_query == "进行中":
                    if not (exp['start_date'] <= today <= exp['end_date']):
                        match = False
                elif status_query == "已完成":
                    if exp['end_date'] >= today:
                        match = False
                elif status_query == "即将开始":
                    if exp['start_date'] <= today:
                        match = False
            
            if match:
                # 计算实验状态
                if exp['end_date'] < today:
                    status = "已完成"
                elif exp['start_date'] <= today <= exp['end_date']:
                    status = "进行中"
                else:
                    status = "即将开始"
                
                # 添加状态信息
                exp_with_status = exp.copy()
                exp_with_status['实验状态'] = status
                exp_with_status['剩余天数'] = (exp['end_date'] - today).days if exp['end_date'] >= today else 0
                exp_with_status['数据状态'] = "活跃"  # 标识数据来源
                active_results.append(exp_with_status)
        
        # 2. 智能判断是否需要搜索归档数据
        need_archive_search = False
        archive_search_reasons = []  # 记录触发归档搜索的原因
        
        # 首先检查用户是否要求包含归档数据
        if include_archived:
            # 强制搜索归档数据（用户明确要求）
            if force_archive_search:
                need_archive_search = True
                archive_search_reasons.append("用户强制要求")
            else:
                # 条件1：活跃数据结果较少（少于5条）
                if len(active_results) < 5:
                    need_archive_search = True
                    archive_search_reasons.append("活跃数据结果较少")
                
                # 条件2：查询的是历史日期范围（结束日期早于今天）
                if end_date_query < today:
                    need_archive_search = True
                    archive_search_reasons.append("查询历史日期范围")
                
                # 条件3：用户明确查询已完成的实验
                if status_query == "已完成":
                    need_archive_search = True
                    archive_search_reasons.append("查询已完成实验")
                
                # 条件4：新增 - 如果用户设置了特定的日期范围查询，且该范围可能包含历史数据
                # 计算查询日期范围的天数跨度
                date_span_days = (end_date_query - start_date_query).days
                if date_span_days > 60:  # 如果查询跨度超过60天，很可能包含历史数据
                    need_archive_search = True
                    archive_search_reasons.append("查询跨度较大")
                
                # 条件5：新增 - 如果开始日期早于今天，说明查询范围包含历史数据
                if start_date_query < today:
                    need_archive_search = True
                    archive_search_reasons.append("查询范围包含历史数据")
                
                # 条件6：新增 - 如果用户明确设置了较早的日期范围，强制搜索归档数据
                # 检查是否有明显的"历史查询意图"
                if start_date_query < (today - timedelta(days=90)):  # 查询90天前的数据
                    need_archive_search = True
                    archive_search_reasons.append("查询较早历史数据")
        
        # 3. 搜索归档数据（如果需要）
        archived_results = []
        if need_archive_search:
            # 显示归档搜索原因
            if archive_search_reasons:
                st.info(f"🔍 系统将搜索归档数据，原因：{', '.join(archive_search_reasons)}")
            
            try:
                from utils.data_archive import DataArchiver
                archiver = DataArchiver()
                
                # 构建归档查询条件
                archive_filters = {}
                if batch_query:
                    archive_filters['sample_batch'] = batch_query
                if method_query != "全部":
                    archive_filters['method_name'] = method_query
                if start_date_query or end_date_query:
                    archive_filters['date_range'] = (start_date_query, end_date_query)
                
                # 搜索归档数据
                archived_data = archiver.restore_archived_experiments(**archive_filters)
                
                # 处理归档数据结果
                for exp in archived_data:
                    # 应用相同的筛选条件
                    match = True
                    
                    # 实验序号筛选
                    if exp_id_query and exp.get('exp_id') != exp_id_query:
                        match = False
                    
                    # 日期范围筛选（需要转换字符串日期）
                    if 'start_date' in exp and 'end_date' in exp:
                        try:
                            exp_start = date.fromisoformat(exp['start_date']) if isinstance(exp['start_date'], str) else exp['start_date']
                            exp_end = date.fromisoformat(exp['end_date']) if isinstance(exp['end_date'], str) else exp['end_date']
                            
                            if exp_start > end_date_query or exp_end < start_date_query:
                                match = False
                        except:
                            match = False
                    
                    # 检测方法筛选
                    if method_query != "全部" and exp.get('method_name') != method_query:
                        match = False
                    
                    # 样品批号筛选
                    if batch_query and batch_query.lower() not in exp.get('sample_batch', '').lower():
                        match = False
                    
                    # 备注筛选
                    if notes_query and notes_query.lower() not in exp.get('notes', '').lower():
                        match = False
                    
                    if match:
                        # 计算实验状态（归档数据都是已完成的）
                        status = "已完成"
                        
                        # 添加状态信息
                        exp_with_status = exp.copy()
                        exp_with_status['实验状态'] = status
                        exp_with_status['剩余天数'] = 0  # 归档数据已完成
                        exp_with_status['数据状态'] = "已归档"  # 标识数据来源
                        exp_with_status['归档时间'] = exp.get('archived_at', '未知')
                        exp_with_status['归档原因'] = exp.get('archive_reason', '未知')
                        archived_results.append(exp_with_status)
                        
            except Exception as e:
                st.warning(f"⚠️ 搜索归档数据时出现错误: {e}")
        else:
            # 如果没有搜索归档数据，显示原因
            if include_archived:
                st.info("ℹ️ 当前查询条件下无需搜索归档数据")
        
        # 4. 合并结果
        query_results = active_results + archived_results
        
        # 显示查询结果
        if not query_results:
            st.info("🔍 未找到符合条件的实验")
        else:
            # 统计活跃和归档数据数量
            active_count = len([exp for exp in query_results if exp.get('数据状态') == '活跃'])
            archived_count = len([exp for exp in query_results if exp.get('数据状态') == '已归档'])
            
            # 显示结果统计
            if archived_count > 0:
                st.success(f"✅ 找到 {len(query_results)} 条符合条件的实验（活跃: {active_count}, 已归档: {archived_count}）")
                st.info("💡 系统已智能包含归档数据，为您提供完整的查询结果")
            else:
                st.success(f"✅ 找到 {len(query_results)} 条符合条件的实验")
            
            # 创建结果表格
            result_data = []
            for exp in query_results:
                result_data.append({
                    '实验序号': f"#{exp['exp_id']}",
                    '样品批号': exp['sample_batch'],
                    '检测方法': exp['method_name'],
                    '开始日期': exp['start_date'],
                    '结束日期': exp['end_date'],
                    '实验状态': exp['实验状态'],
                    '剩余天数': exp['剩余天数'],
                    '总天数': exp.get('total_days', '未知'),
                    '数据状态': exp.get('数据状态', '活跃'),
                    '备注': exp.get('notes', '')
                })
            
            # 如果是归档数据，添加归档信息
            if any(exp.get('数据状态') == '已归档' for exp in query_results):
                for i, exp in enumerate(query_results):
                    if exp.get('数据状态') == '已归档':
                        result_data[i]['归档时间'] = exp.get('归档时间', '未知')
                        result_data[i]['归档原因'] = exp.get('归档原因', '未知')
            
            # 显示表格
            df = pd.DataFrame(result_data)
            st.dataframe(df, use_container_width=True)
            
            # 导出功能
            col1, col2 = st.columns(2)
            with col1:
                if st.button("📥 导出到Excel", use_container_width=True):
                    filename = f"实验查询结果_{date.today().strftime('%Y%m%d_%H%M%S')}.xlsx"
                    df.to_excel(filename, index=False, engine='openpyxl')
                    st.success(f"已导出到: {filename}")
            
            with col2:
                csv = df.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(
                    label="📥 下载CSV",
                    data=csv,
                    file_name=f"实验查询结果_{date.today().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            
            # 统计信息
            st.markdown("---")
            st.subheader("📈 查询结果统计")
            
            # 实验状态统计
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("总实验数", len(query_results))
            with col2:
                status_counts = df['实验状态'].value_counts()
                st.metric("进行中", status_counts.get('进行中', 0))
            with col3:
                st.metric("已完成", status_counts.get('已完成', 0))
            with col4:
                st.metric("即将开始", status_counts.get('即将开始', 0))
            
            # 数据状态统计
            if archived_count > 0:
                st.markdown("---")
                st.subheader("🗂️ 数据来源统计")
                
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("活跃数据", active_count)
                with col2:
                    st.metric("已归档数据", archived_count)
                
                # 显示归档数据说明
                st.info("📋 **归档数据说明**: 已归档的实验数据仍然完整保存，可以正常查询和导出。归档是为了提高系统性能，不影响数据完整性。")

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
            
            # 支持多行样品批号输入，实现批量添加
            sample_batches = st.text_area(
                "样品批号", 
                placeholder="请输入样品批号\n支持多个批号，每行一个\n或使用逗号分隔",
                help="支持多种格式：\n1. 每行一个批号\n2. 逗号分隔的批号\n3. 单个批号"
            )
        
        with col2:
            # 实验序号输入 - 支持手动输入或自动生成
            exp_id_input = st.number_input(
                "实验序号",
                min_value=1,
                value=1,
                help="请输入实验序号，或留空自动生成"
            )
            
            methods = list(get_cytotoxic_methods().keys())
            method_name = st.selectbox("检测方法", methods)
            
            notes = st.text_area("备注", placeholder="请输入备注信息")
        
        submitted = st.form_submit_button("添加实验")
        
        if submitted:
            if not sample_batches.strip():
                st.error("请输入样品批号")
                return
            
            # 解析样品批号（支持多行和逗号分隔）
            batch_list = []
            for line in sample_batches.strip().split('\n'):
                line = line.strip()
                if line:
                    # 处理逗号分隔的情况
                    if ',' in line:
                        batch_list.extend([b.strip() for b in line.split(',') if b.strip()])
                    else:
                        batch_list.append(line)
            
            # 去重并过滤空值
            batch_list = list(set([b for b in batch_list if b]))
            
            if not batch_list:
                st.error("未找到有效的样品批号")
                return
            
            # 显示将要添加的批号
            if len(batch_list) > 1:
                if exp_id_input > 1:
                    st.info(f"将添加 {len(batch_list)} 个样品批号，所有批号使用实验序号 {exp_id_input}：{', '.join(batch_list)}")
                else:
                    st.info(f"将添加 {len(batch_list)} 个样品批号：{', '.join(batch_list)}")
            
            # 批量添加实验
            success_count = 0
            failed_batches = []
            
            with st.spinner("正在批量添加实验..."):
                for i, batch in enumerate(batch_list):
                    try:
                        # 验证数据
                        is_valid, message = scheduler.validate_experiment_data(
                            start_date.strftime('%Y-%m-%d'), method_name, batch
                        )
                        
                        if not is_valid:
                            failed_batches.append(f"{batch}: {message}")
                            continue
                        
                        # 计算当前批次的实验序号 - 所有批号使用相同序号
                        current_exp_id = exp_id_input if exp_id_input >= 1 else None
                        
                        # 添加实验 - 批量添加时允许重复的实验序号
                        if add_experiment(start_date.strftime('%Y-%m-%d'), method_name, batch, notes, current_exp_id, allow_duplicate_exp_id=True):
                            success_count += 1
                        else:
                            failed_batches.append(f"{batch}: 添加失败")
                    except Exception as e:
                        failed_batches.append(f"{batch}: {str(e)}")
            
            # 显示结果
            if success_count > 0:
                st.rerun()

def render_edit_form():
    """渲染实验编辑表单"""
    if 'editing_experiment' not in st.session_state or st.session_state.editing_experiment is None:
        return
    
    exp = st.session_state.editing_experiment
    
    st.subheader("编辑实验")
    st.info(f"正在编辑实验 #{exp['exp_id']}: {exp['sample_batch']} - {exp['method_name']}")
    
    with st.form("edit_experiment_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            start_date = st.date_input(
                "上样日期",
                value=exp['start_date'],
                format="YYYY-MM-DD"
            )
            
            sample_batch = st.text_input(
                "样品批号", 
                value=exp['sample_batch'],
                placeholder="请输入样品批号"
            )
        
        with col2:
            methods = list(get_cytotoxic_methods().keys())
            method_name = st.selectbox(
                "检测方法", 
                methods,
                index=methods.index(exp['method_name']) if exp['method_name'] in methods else 0
            )
            
            notes = st.text_area(
                "备注", 
                value=exp['notes'],
                placeholder="请输入备注信息"
            )
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            submitted = st.form_submit_button("保存修改")
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
                
                # 更新实验
                if update_experiment(
                    st.session_state.editing_index,
                    start_date.strftime('%Y-%m-%d'),
                    method_name,
                    sample_batch,
                    notes
                ):
                    st.rerun()
        
        with col2:
            if st.form_submit_button("取消编辑"):
                st.session_state.editing_index = None
                st.session_state.editing_experiment = None
                st.rerun()
        
        with col3:
            if st.form_submit_button("删除实验"):
                if delete_experiment(st.session_state.editing_index):
                    st.session_state.editing_index = None
                    st.session_state.editing_experiment = None
                    st.rerun()

def render_experiment_list():
    """渲染聚合实验列表"""
    if not st.session_state.experiments:
        st.info("暂无实验数据")
        return
    
    st.subheader("实验列表")
    
    # 显示总体统计
    total_experiments = len(st.session_state.experiments)
    unique_exp_ids = len(set(exp.get('exp_id') for exp in st.session_state.experiments))
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("总实验数", total_experiments)
    with col2:
        st.metric("实验序号数", unique_exp_ids)
    with col3:
        st.metric("平均批号/序号", f"{total_experiments/unique_exp_ids:.1f}" if unique_exp_ids > 0 else "0")
    
    st.markdown("---")
    
    # 按实验序号聚合实验数据
    grouped_experiments = {}
    for i, exp in enumerate(st.session_state.experiments):
        exp_id = exp.get('exp_id', 'unknown')
        if exp_id not in grouped_experiments:
            grouped_experiments[exp_id] = []
        grouped_experiments[exp_id].append((i, exp))
    
    # 按实验序号排序显示
    for exp_id in sorted(grouped_experiments.keys()):
        experiments_group = grouped_experiments[exp_id]
        
        # 获取第一个实验的基本信息作为组信息
        first_exp = experiments_group[0][1]
        batch_count = len(experiments_group)
        
        # 收集所有批号
        all_batches = [exp[1]['sample_batch'] for exp in experiments_group]
        batch_summary = ", ".join(all_batches[:3])  # 显示前3个批号
        if batch_count > 3:
            batch_summary += f"... (共{batch_count}个)"
        
        # 计算实验状态
        today = date.today()
        if first_exp['end_date'] < today:
            status_emoji = "✅"
            status_text = "已完成"
        elif first_exp['start_date'] <= today <= first_exp['end_date']:
            status_emoji = "🔬"
            status_text = "进行中"
        else:
            status_emoji = "⏰"
            status_text = "即将开始"
        
        # 实验序号级别的展开器
        with st.expander(f"{status_emoji} 实验#{exp_id} - {first_exp['start_date']} - {first_exp['method_name']} ({batch_count}个批号) - {status_text}"):
            
            # 显示实验序号级别的基本信息
            col_info, col_actions = st.columns([4, 1])
            with col_info:
                st.markdown(f"**实验序号**: #{exp_id}")
                st.markdown(f"**检测方法**: {first_exp['method_name']}")
                st.markdown(f"**开始日期**: {first_exp['start_date']}")
                st.markdown(f"**结束日期**: {first_exp['end_date']}")
                st.markdown(f"**样品批号**: {batch_summary}")
                if first_exp['notes']:
                    st.markdown(f"**备注**: {first_exp['notes']}")
            
            with col_actions:
                # 实验序号级别的批量操作
                delete_key = f"delete_all_{exp_id}"
                confirm_key = f"confirm_delete_all_{exp_id}"
                archive_key = f"archive_all_{exp_id}"
                confirm_archive_key = f"confirm_archive_all_{exp_id}"
                
                # 检查是否在确认删除状态
                if st.session_state.get(confirm_key, False):
                    # 显示确认删除界面
                    st.warning(f"⚠️ 确认删除实验#{exp_id}的全部{batch_count}个批号？")
                    col_confirm1, col_confirm2 = st.columns(2)
                    
                    with col_confirm1:
                        if st.button("✅ 确认删除", key=f"execute_delete_{exp_id}", type="primary"):
                            # 使用专门的批量删除函数
                            deleted_count = delete_experiments_by_exp_id(exp_id)
                            
                            if deleted_count > 0:
                                st.success(f"✅ 已成功删除实验#{exp_id}的全部{deleted_count}个批号")
                                # 清除确认状态
                                st.session_state[confirm_key] = False
                                st.rerun()
                            else:
                                st.error("❌ 删除失败，请重试")
                    
                    with col_confirm2:
                        if st.button("❌ 取消", key=f"cancel_delete_{exp_id}", type="secondary"):
                            st.session_state[confirm_key] = False
                            st.rerun()
                
                # 检查是否在确认归档状态
                elif st.session_state.get(confirm_archive_key, False):
                    # 显示确认归档界面
                    st.warning(f"🗂️ 确认归档实验#{exp_id}的全部{batch_count}个批号？\n\n归档后数据将压缩存储，不再在主列表中显示。")
                    col_confirm1, col_confirm2 = st.columns(2)
                    
                    with col_confirm1:
                        if st.button("✅ 确认归档", key=f"execute_archive_{exp_id}", type="primary"):
                            # 执行归档
                            archived_data, archived_count = manual_archive_by_exp_id(
                                st.session_state.experiments, exp_id
                            )
                            
                            if archived_count > 0:
                                # 更新session state
                                st.session_state.experiments = archived_data
                                # 保存到文件
                                save_experiments(archived_data)
                                st.success(f"✅ 已成功归档实验#{exp_id}的全部{archived_count}个批号")
                                # 清除确认状态
                                st.session_state[confirm_archive_key] = False
                                st.rerun()
                            else:
                                st.error("❌ 归档失败，请重试")
                    
                    with col_confirm2:
                        if st.button("❌ 取消", key=f"cancel_archive_{exp_id}", type="secondary"):
                            st.session_state[confirm_archive_key] = False
                            st.rerun()
                
                else:
                    # 显示操作按钮
                    col_btn1, col_btn2 = st.columns(2)
                    
                    with col_btn1:
                        if st.button(f"🗑️ 删除全部", key=delete_key, type="secondary", 
                                   help=f"删除实验#{exp_id}下的所有{batch_count}个批号"):
                            st.session_state[confirm_key] = True
                            st.rerun()
                    
                    with col_btn2:
                        if st.button(f"🗂️ 归档全部", key=archive_key, type="secondary", 
                                   help=f"归档实验#{exp_id}下的所有{batch_count}个批号到压缩存储"):
                            st.session_state[confirm_archive_key] = True
                            st.rerun()
            
            st.markdown("---")
            
            # 批号级别的详细信息
            st.markdown("**批号详情:**")
            
            for i, (original_index, exp) in enumerate(experiments_group):
                # 使用嵌套的expander显示每个批号的详细信息
                with st.expander(f"📦 批号: {exp['sample_batch']}", expanded=False):
                    col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
                    
                    with col1:
                        st.markdown(f"**样品批号**: {exp['sample_batch']}")
                        st.markdown(f"**开始日期**: {exp['start_date']}")
                        st.markdown(f"**结束日期**: {exp['end_date']}")
                        if exp['notes']:
                            st.markdown(f"**备注**: {exp['notes']}")
                    
                    with col2:
                        st.markdown("**实验步骤:**")
                        for step in exp['steps']:
                            # 显示步骤信息，包括是否被调整
                            if step.get('was_adjusted', False):
                                st.markdown(f"• 第{step['relative_day']}天: {step['step_name']} ⚠️")
                                st.markdown(f"  📅 {step['scheduled_date']} (已调整)")
                                if step.get('original_date'):
                                    st.markdown(f"  📅 原计划: {step['original_date']}")
                            else:
                                st.markdown(f"• 第{step['relative_day']}天: {step['step_name']}")
                                st.markdown(f"  📅 {step['scheduled_date']}")
                    
                    with col3:
                        if st.button(f"编辑", key=f"edit_{original_index}_{i}"):
                            edit_experiment(original_index)
                            st.rerun()
                    
                    with col4:
                        # 批号级别的操作按钮
                        col_delete, col_archive = st.columns(2)
                        
                        with col_delete:
                            if st.button(f"🗑️", key=f"delete_{original_index}_{i}", 
                                       help="删除此批号"):
                                delete_experiment(original_index)
                                st.rerun()
                        
                        with col_archive:
                            if st.button(f"🗂️", key=f"archive_{original_index}_{i}", 
                                       help="归档此批号到压缩存储"):
                                # 执行单个批号归档
                                archived_data, archived_count = manual_archive_by_sample_batch(
                                    st.session_state.experiments, exp['sample_batch']
                                )
                                
                                if archived_count > 0:
                                    # 更新session state
                                    st.session_state.experiments = archived_data
                                    # 保存到文件
                                    save_experiments(archived_data)
                                    st.success(f"✅ 已成功归档批号 {exp['sample_batch']}")
                                    st.rerun()
                                else:
                                    st.error("❌ 归档失败，请重试")

def render_today_experiments():
    """渲染当天实验安排 - 首页醒目显示"""
    st.markdown("---")
    
    # 获取当天日期
    today = date.today()
    today_str = today.strftime('%Y年%m月%d日')
    today_key = today.strftime('%Y-%m-%d')  # 用于比较的日期键
    
    
    # 获取当天的实验安排 - 按实验序号和步骤聚合，避免重复显示
    today_tasks_grouped = {}
    
    for exp in st.session_state.experiments:
        for step in exp["steps"]:
            # 检查这个步骤是否在今天执行 - 使用字符串比较避免日期对象问题
            if step["date_str"] == today_key:
                # 创建聚合键：(实验序号, 步骤名称)
                group_key = (exp["exp_id"], step["step_name"])
                
                if group_key not in today_tasks_grouped:
                    today_tasks_grouped[group_key] = {
                        "exp_id": exp["exp_id"],
                        "step_name": step["step_name"],
                        "description": step["description"],
                        "relative_day": step["relative_day"],
                        "method_name": exp["method_name"],
                        "notes": exp["notes"],
                        "start_date": exp["start_date"].strftime("%Y-%m-%d"),
                        "batches": []  # 存储所有相关的批号信息
                    }
                
                # 添加批号信息
                today_tasks_grouped[group_key]["batches"].append({
                    "sample_batch": exp["sample_batch"],
                    "notes": exp["notes"]
                })
    
    # 转换为列表格式，便于后续处理
    today_tasks = list(today_tasks_grouped.values())
    
    # 显示聚合信息
    if today_tasks:
        total_batches = sum(len(task['batches']) for task in today_tasks)
        st.success(f"✅ 找到 {len(today_tasks)} 个实验任务，包含 {total_batches} 个批号")
    else:
        st.warning("⚠️ 今天没有实验安排")
    
    # 根据是否有实验设置不同的背景色和样式
    if today_tasks:
        # 有实验 - 红色背景
        st.markdown(f"""
        <div style="
            background: linear-gradient(135deg, #ff6b6b, #ee5a52);
            border: 3px solid #d32f2f;
            border-radius: 15px;
            padding: 25px;
            margin: 20px 0;
            text-align: center;
            box-shadow: 0 8px 32px rgba(255, 107, 107, 0.3);
        ">
            <h1 style="
                color: white;
                font-size: 2.5em;
                font-weight: bold;
                margin: 0;
                text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
                font-family: 'Microsoft YaHei', sans-serif;
            ">
                🔴 今日实验安排
            </h1>
            <p style="
                color: white;
                font-size: 1.2em;
                margin: 10px 0 20px 0;
                opacity: 0.9;
            ">
                📅 {today_str} - 共 {len(today_tasks)} 个实验任务
            </p>
            <p style="
                color: white;
                font-size: 1.0em;
                margin: 5px 0 15px 0;
                opacity: 0.8;
            ">
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        # 显示具体的实验任务
        for i, task in enumerate(today_tasks):
            # 准备批号显示信息
            batch_count = len(task['batches'])
            if batch_count == 1:
                batch_display = f"批号: {task['batches'][0]['sample_batch']}"
            else:
                batch_names = [batch['sample_batch'] for batch in task['batches']]
                batch_display = f"批号: {', '.join(batch_names)} (共{batch_count}个)"
            
            # 准备备注显示信息（如果有多个批号，显示第一个非空备注或"无"）
            notes_display = "无"
            for batch in task['batches']:
                if batch['notes'] and batch['notes'].strip():
                    notes_display = batch['notes']
                    break
            
            st.markdown(f"""
            <div style="
                background: linear-gradient(135deg, #fff3e0, #ffe0b2);
                border: 2px solid #ff9800;
                border-radius: 10px;
                padding: 20px;
                margin: 15px 0;
                box-shadow: 0 4px 16px rgba(255, 152, 0, 0.2);
            ">
                <h2 style="
                    color: #e65100;
                    font-size: 1.8em;
                    margin: 0 0 15px 0;
                    font-family: 'Microsoft YaHei', sans-serif;
                ">
                    🧪 实验#{task['exp_id']} - {task['step_name']}
                </h2>
                <div style="
                    background: white;
                    border-radius: 8px;
                    padding: 15px;
                    margin: 10px 0;
                ">
                    <p style="
                        color: #333;
                        font-size: 1.1em;
                        margin: 8px 0;
                        font-family: 'Microsoft YaHei', sans-serif;
                    ">
                        <strong>🔬 检测方法:</strong> {task['method_name']}
                    </p>
                    <p style="
                        color: #333;
                        font-size: 1.1em;
                        margin: 8px 0;
                        font-family: 'Microsoft YaHei', sans-serif;
                    ">
                        <strong>📦 {batch_display}</strong>
                    </p>
                    <p style="
                        color: #333;
                        font-size: 1.1em;
                        margin: 8px 0;
                        font-family: 'Microsoft YaHei', sans-serif;
                    ">
                        <strong>📝 备注:</strong> {notes_display}
                    </p>
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        # 添加提醒信息
        st.markdown(f"""
        <div style="
            background: linear-gradient(135deg, #ffebee, #ffcdd2);
            border: 2px solid #f44336;
            border-radius: 10px;
            padding: 15px;
            margin: 20px 0;
            text-align: center;
        ">
            <p style="
                color: #d32f2f;
                font-size: 1.3em;
                font-weight: bold;
                margin: 0;
                font-family: 'Microsoft YaHei', sans-serif;
            ">
                ⚠️ 今日有 {len(today_tasks)} 个实验任务需要完成！
            </p>
            <p style="
                color: #d32f2f;
                font-size: 1.0em;
                margin: 5px 0 0 0;
                opacity: 0.9;
                font-family: 'Microsoft YaHei', sans-serif;
            ">
                📊 已聚合 {sum(len(task['batches']) for task in today_tasks)} 个批号
            </p>
        </div>
        """, unsafe_allow_html=True)
        
    else:
        # 没有实验 - 绿色背景
        st.markdown(f"""
        <div style="
            background: linear-gradient(135deg, #4caf50, #66bb6a);
            border: 3px solid #388e3c;
            border-radius: 15px;
            padding: 25px;
            margin: 20px 0;
            text-align: center;
            box-shadow: 0 8px 32px rgba(76, 175, 80, 0.3);
        ">
            <h1 style="
                color: white;
                font-size: 2.5em;
                font-weight: bold;
                margin: 0;
                text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
                font-family: 'Microsoft YaHei', sans-serif;
            ">
                🟢 今日无实验安排
            </h1>
            <p style="
                color: white;
                font-size: 1.2em;
                margin: 10px 0 20px 0;
                opacity: 0.9;
            ">
                📅 {today_str} - 可以休息或准备明天的实验
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        # 显示明天的实验安排（如果有）
        tomorrow = today + timedelta(days=1)
        tomorrow_key = tomorrow.strftime('%Y-%m-%d')
        
        # 获取明天的实验安排
        tomorrow_tasks_grouped = {}
        for exp in st.session_state.experiments:
            for step in exp["steps"]:
                if step["date_str"] == tomorrow_key:
                    group_key = (exp["exp_id"], step["step_name"])
                    if group_key not in tomorrow_tasks_grouped:
                        tomorrow_tasks_grouped[group_key] = {
                            "exp_id": exp["exp_id"],
                            "step_name": step["step_name"],
                            "method_name": exp["method_name"],
                            "batches": []
                        }
                    tomorrow_tasks_grouped[group_key]["batches"].append(exp["sample_batch"])
        
        tomorrow_tasks = list(tomorrow_tasks_grouped.values())
        
        if tomorrow_tasks:
            st.markdown(f"""
            <div style="
                background: linear-gradient(135deg, #e8f5e8, #c8e6c9);
                border: 2px solid #4caf50;
                border-radius: 10px;
                padding: 20px;
                margin: 20px 0;
            ">
                <h3 style="
                    color: #2e7d32;
                    font-size: 1.5em;
                    margin: 0 0 15px 0;
                    font-family: 'Microsoft YaHei', sans-serif;
                ">
                    🔮 明日预告 ({tomorrow.strftime('%m月%d日')})
                </h3>
                <p style="
                    color: #2e7d32;
                    font-size: 1.1em;
                    margin: 0;
                    font-family: 'Microsoft YaHei', sans-serif;
                ">
                    明天将有 {len(tomorrow_tasks)} 个实验任务
                </p>
            </div>
            """, unsafe_allow_html=True)

def render_notification_settings():
    """渲染通知设置"""
    st.subheader("通知设置")
    
    settings = get_notification_settings()
    
    # 智能Webhook配置显示（在表单外部）
    has_webhook = settings["webhook_url"] and settings["webhook_url"].strip()
    
    if has_webhook:
        # 已配置时显示"已配置apikey"和修改选项
        col1, col2 = st.columns([3, 1])
        with col1:
            st.info(f"✅ 已配置Webhook地址: {settings['webhook_url'][:50]}...")
        with col2:
            if st.button("✏️ 修改配置", type="secondary"):
                st.session_state.editing_webhook = True
                st.rerun()
        
        # 如果正在编辑，显示输入框
        if st.session_state.get('editing_webhook', False):
            st.markdown("**修改Webhook配置**")
            webhook_url = st.text_input(
                "企业微信Webhook地址",
                value="",
                placeholder="请输入新的Webhook地址，留空则保持原配置"
            )
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("💾 保存新配置", type="primary"):
                    if webhook_url and webhook_url.strip():
                        # 验证新地址
                        is_valid, message = validate_webhook_url(webhook_url)
                        if not is_valid:
                            st.error(message)
                            return
                        
                        # 更新设置
                        success = update_notification_settings(
                            enabled=settings["enabled"],
                            webhook_url=webhook_url,
                            push_time=settings["push_time"]
                        )
                        
                        if success:
                            st.session_state.editing_webhook = False
                            st.success("Webhook地址已更新")
                            st.rerun()
                        else:
                            st.error("更新失败")
                    else:
                        st.warning("请输入新的Webhook地址")
            
            with col2:
                if st.button("❌ 取消修改"):
                    st.session_state.editing_webhook = False
                    st.rerun()
            
            st.markdown("---")
        else:
            webhook_url = settings["webhook_url"]
    else:
        # 未配置时显示输入框
        st.markdown("**配置Webhook地址**")
        webhook_url = st.text_input(
            "企业微信Webhook地址",
            value="",
            placeholder="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=..."
        )
        st.markdown("---")
    
    # 主要设置表单
    with st.form("notification_settings"):
        enabled = st.checkbox("启用通知", value=settings["enabled"])
        
        push_time = st.time_input(
            "每日推送时间",
            value=datetime.strptime(settings["push_time"], "%H:%M").time()
        )
        

        
        col1, col2 = st.columns(2)
        
        with col1:
            submitted = st.form_submit_button("保存设置")
            if submitted:
                # 验证webhook地址
                if not has_webhook and (not webhook_url or not webhook_url.strip()):
                    st.error("请先配置Webhook地址")
                    return
                
                # 保存设置
                success = update_notification_settings(
                    enabled=enabled,
                    webhook_url=webhook_url if webhook_url and webhook_url.strip() else settings["webhook_url"],
                    push_time=push_time.strftime("%H:%M")
                )
                
                if success:
                    st.success("设置已保存")
                else:
                    st.error("保存设置失败")
        
        with col2:
            # 占位符
            pass
    
    # 测试连接按钮（在表单外部）
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔗 测试连接", type="secondary"):
            # 获取当前的webhook配置
            current_webhook = webhook_url if 'webhook_url' in locals() and webhook_url and webhook_url.strip() else settings["webhook_url"]
            
            if current_webhook and current_webhook.strip():
                try:
                    success, message = test_notification()
                    if success:
                        st.success(message)
                    else:
                        st.error(message)
                except Exception as e:
                    st.error(f"测试连接失败: {str(e)}")
            else:
                st.warning("请先配置Webhook地址")
    
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
        if st.button("📤 发送今日实验内容", type="primary"):
            if st.session_state.experiments:
                success = send_manual_notification("daily")
                if success:
                    st.success("✅ 今日实验内容已发送成功")
                else:
                    st.error("❌ 发送失败，请检查网络连接和webhook配置")
            else:
                st.warning("⚠️ 暂无实验数据可发送")
    
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
            ["首页", "实验管理", "日历视图", "周视图", "每日汇总", "实验查询", "通知设置", "系统信息"]
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
    if page == "首页":
        # 显示当天实验安排
        render_today_experiments()
        
        # 显示快速统计
        st.markdown("---")
        st.subheader("📊 快速统计")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            # 计算今日实验数量（按实验序号聚合后的数量）
            today = date.today()
            today_key = today.strftime('%Y-%m-%d')
            today_tasks_grouped = {}
            
            for exp in st.session_state.experiments:
                for step in exp["steps"]:
                    if step["date_str"] == today_key:
                        group_key = (exp["exp_id"], step["step_name"])
                        if group_key not in today_tasks_grouped:
                            today_tasks_grouped[group_key] = True
            
            today_count = len(today_tasks_grouped)
            st.metric("今日实验", today_count)
        with col2:
            st.metric("本周实验", len([exp for exp in st.session_state.experiments if exp['start_date'] <= date.today() <= exp['end_date']]))
        with col3:
            st.metric("总实验数", len(st.session_state.experiments))
        with col4:
            upcoming = scheduler.get_upcoming_experiments(st.session_state.experiments, 7)
            st.metric("7天内实验", len(upcoming))
        
        # 显示最近实验
        st.markdown("---")
        st.subheader("🔬 最近实验")
        
        if st.session_state.experiments:
            # 筛选从今天开始1个月内的所有实验进行中的数据
            today = date.today()
            one_month_later = today + timedelta(days=30)
            ongoing_experiments = []
            
            for exp in st.session_state.experiments:
                # 检查实验是否在从今天开始1个月内的进行中数据
                if exp['start_date'] <= one_month_later and exp['end_date'] >= today:
                    ongoing_experiments.append(exp)
            
            if ongoing_experiments:
                # 按开始日期排序，显示所有符合条件的实验
                ongoing_experiments.sort(key=lambda x: x['start_date'], reverse=True)
                
                st.success(f"✅ 找到 {len(ongoing_experiments)} 个从今天开始1个月内的实验")
                
                # 按实验序号聚合
                exp_id_groups = {}
                for exp in ongoing_experiments:
                    exp_id = exp['exp_id']
                    if exp_id not in exp_id_groups:
                        exp_id_groups[exp_id] = []
                    exp_id_groups[exp_id].append(exp)
                
                # 显示聚合后的实验
                for exp_id, experiments in sorted(exp_id_groups.items(), key=lambda x: x[0]):
                    # 获取该实验序号下的第一个实验信息用于显示
                    first_exp = experiments[0]
                    
                    # 计算实验进度
                    total_days = (first_exp['end_date'] - first_exp['start_date']).days + 1
                    days_elapsed = (today - first_exp['start_date']).days + 1
                    progress_percentage = min(100, max(0, (days_elapsed / total_days) * 100))
                    
                    # 确定实验状态
                    if first_exp['end_date'] < today:
                        status = "已完成"
                        status_color = "🔴"
                    elif first_exp['start_date'] <= today <= first_exp['end_date']:
                        status = "进行中"
                        status_color = "🟢"
                    else:
                        status = "即将开始"
                        status_color = "🟡"
                    
                    # 聚合显示：只显示实验序号，不显示具体批号
                    with st.expander(f"{status_color} 实验#{exp_id} - {first_exp['method_name']} ({status})"):
                        # 显示该实验序号下的所有批号
                        for i, exp in enumerate(experiments):
                            if i > 0:
                                st.markdown("---")  # 分隔线
                            
                            col1, col2 = st.columns([2, 1])
                            with col1:
                                st.markdown(f"**实验序号**: #{exp['exp_id']}")
                                st.markdown(f"**样品批号**: {exp['sample_batch']}")
                                st.markdown(f"**检测方法**: {exp['method_name']}")
                                st.markdown(f"**开始日期**: {exp['start_date']}")
                                st.markdown(f"**结束日期**: {exp['end_date']}")
                                st.markdown(f"**实验状态**: {status}")
                                if exp['notes']:
                                    st.markdown(f"**备注**: {exp['notes']}")
                            
                            with col2:
                                st.markdown("**实验步骤:**")
                                for step in exp['steps']:
                                    # 显示步骤信息，包括是否被调整
                                    if step.get('was_adjusted', False):
                                        st.markdown(f"• 第{step['relative_day']}天: {step['step_name']} ⚠️")
                                        st.markdown(f"  📅 {step['scheduled_date']} (已调整)")
                                        if step.get('original_date'):
                                            st.markdown(f"  📅 原计划: {step['original_date']}")
                                    else:
                                        st.markdown(f"• 第{step['relative_day']}天: {step['step_name']}")
                                        st.markdown(f"  📅 {step['scheduled_date']}")
                            
                            # 显示进度条（仅对进行中的实验）
                            if status == "进行中":
                                st.markdown(f"**实验进度**: {days_elapsed}/{total_days} 天 ({progress_percentage:.1f}%)")
                                st.progress(progress_percentage / 100)
                            elif status == "即将开始":
                                days_until_start = (exp['start_date'] - today).days
                                st.markdown(f"**距离开始**: {days_until_start} 天")
                            elif status == "已完成":
                                days_since_end = (today - exp['end_date']).days
                                st.markdown(f"**完成天数**: {days_since_end} 天")
            else:
                st.info("📅 从今天开始1个月内没有实验安排")
        else:
            st.info("暂无实验数据")
    
    elif page == "实验管理":
        # 检查是否正在编辑
        if st.session_state.editing_experiment is not None:
            render_edit_form()
        else:
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
    
    elif page == "实验查询":
        render_experiment_query()
    
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
            
            # 数据归档统计
            st.markdown("---")
            st.markdown("**📦 数据归档统计**")
            
            try:
                archive_stats = get_archive_statistics()
                if archive_stats:
                    st.info(f"归档实验总数: {archive_stats.get('total_archived', 0)}")
                    st.info(f"归档文件大小: {archive_stats.get('archive_size_mb', 0)} MB")
                    
                    # 显示年份分布
                    year_dist = archive_stats.get('year_distribution', {})
                    if year_dist:
                        st.markdown("**年份分布:**")
                        for year, count in sorted(year_dist.items()):
                            st.info(f"{year}年: {count}个实验")
                    
                    # 最后归档时间
                    last_archive = archive_stats.get('last_archive_date', '')
                    if last_archive:
                        st.info(f"最后归档时间: {last_archive}")
                else:
                    st.info("暂无归档数据")
            except Exception as e:
                st.warning(f"获取归档统计失败: {e}")
            

            
            st.markdown("---")
            st.markdown("**排班配置**")
            
            # 加载当前配置
            from config.settings import load_settings, update_settings
            settings = load_settings()
            
            # 工作日调整选项
            adjust_workdays = st.checkbox(
                "自动调整到工作日", 
                value=settings.get("scheduling", {}).get("adjust_workdays", True),
                help="如果实验步骤落在周末或节假日，根据检测方法规则自动调整到工作日"
            )
            
            # 显示调整规则说明
            st.info("""
            **📋 工作日调整规则说明：**
            
            • **7天计数增值度法、USP显微镜法、MTT-GB14233.2、MTT-ISO等同16886**：严格按照标准规定执行，不进行日期调整
            
            • **日本药局方**：前2天（上样、换液）不调整，最后1天计数可在第9/10/11天中选择非休息日
            """)
            
            # 保存配置按钮
            if st.button("💾 保存排班配置", type="primary"):
                # 更新配置
                if "scheduling" not in settings:
                    settings["scheduling"] = {}
                settings["scheduling"]["adjust_workdays"] = adjust_workdays
                
                # 保存到文件
                update_settings(settings)
                st.success("✅ 排班配置已保存！")
                
                # 提示用户重新创建实验以应用新配置
                st.warning("⚠️ 注意：新配置只影响新创建的实验，现有实验需要重新创建才能应用新配置。")

if __name__ == "__main__":
    main()
