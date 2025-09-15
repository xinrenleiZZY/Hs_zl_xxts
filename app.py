import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from io import BytesIO
import smtplib
from email.mime.text import MIMEText
from email.utils import formatdate
import time
import ssl
from smtplib import SMTPException
import pickle  # 用于持久化存储
import os  # 用于文件操作
import time as time_module
import threading

# 页面配置
st.set_page_config(
    page_title="专利缴费管理系统",
    page_icon="📅",
    layout="wide"
)

# 配置文件路径
CONFIG_FILE = "email_config.pkl"
DATA_FILE = "app_data.pkl"  # 数据持久化文件
LOG_FILE = "email_log.txt"  # 邮件发送日志文件

# 初始化会话状态
if 'patent_data' not in st.session_state:
    st.session_state.patent_data = None  # 存储上传的专利数据
if 'last_upload_time' not in st.session_state:
    st.session_state.last_upload_time = None  # 记录上次上传时间
if 'reminder_sent' not in st.session_state:
    st.session_state.reminder_sent = set()  # 记录已发送提醒的专利ID
if 'auto_refresh' not in st.session_state:
    st.session_state.auto_refresh = True  # 自动刷新开关
if 'reminder_days' not in st.session_state:
    st.session_state.reminder_days = 49  # 提醒提前天数默认值
if 'last_email_sent_time' not in st.session_state:
    st.session_state.last_email_sent_time = None  # 上次邮件发送时间
if 'is_first_load' not in st.session_state:
    st.session_state.is_first_load = True  # 标记首次加载
if 'next_scheduled_send' not in st.session_state:
    st.session_state.next_scheduled_send = None


# 邮箱配置会话状态
if 'email_config' not in st.session_state:
    st.session_state.email_config = {
        "sender_email": "",
        "sender_password": "",
        "smtp_server": "smtp.qq.com",
        "smtp_port": 587,
        "receiver_email": "",
        "email_enabled": False
    }
    
# 新增：基于 Streamlit 路由的心跳接口实现
def handle_heartbeat():
    """处理心跳检测请求，返回符合 UptimeRobot 要求的响应"""
    # 获取当前查询参数
    query_params = st.query_params
    
    # 如果访问路径包含 heartbeat 参数，返回心跳响应
    if "heartbeat" in query_params:
        # 构建心跳响应数据
        response = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "last_data_upload": st.session_state.last_upload_time,
            "last_email_sent": st.session_state.last_email_sent_time.isoformat() 
                               if st.session_state.last_email_sent_time is not None else None,
            "service": "patent-management-system"
        }
        
        # 使用 Streamlit 的 markdown 输出纯文本 JSON，避免页面元素干扰监控
        st.markdown(f"""```json\n{response}\n```""", unsafe_allow_html=True)
        
        # 强制终止后续页面渲染，确保响应简洁
        st.stop()

handle_heartbeat()

# 数据持久化核心函数 - 增强版
def load_persistent_data():
    """从本地文件加载持久化数据到session_state，增强错误处理"""
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'rb') as f:
                data = pickle.load(f)
                # 恢复专利数据
                if 'patent_data' in data:
                    st.session_state.patent_data = data['patent_data']
                # 恢复上传时间
                if 'last_upload_time' in data:
                    st.session_state.last_upload_time = data['last_upload_time']
                # 恢复已发送提醒记录
                if 'reminder_sent' in data:
                    st.session_state.reminder_sent = data['reminder_sent']
                # 恢复提醒天数设置
                if 'reminder_days' in data:
                    st.session_state.reminder_days = data['reminder_days']
                # 恢复上次邮件发送时间（增加格式验证）
                if 'last_email_sent_time' in data:
                    if isinstance(data['last_email_sent_time'], datetime):
                        st.session_state.last_email_sent_time = data['last_email_sent_time']
                    else:
                        st.warning("上次发送时间格式无效，已重置")
                        st.session_state.last_email_sent_time = None

                if 'next_scheduled_send' in data:
                    if isinstance(data['next_scheduled_send'], datetime):
                        st.session_state.next_scheduled_send = data['next_scheduled_send']
                    else:
                        st.warning("计划发送时间格式无效，已重置")
                        st.session_state.next_scheduled_send = datetime.now() + timedelta(minutes=3)
        except Exception as e:
            st.error(f"加载数据失败：{str(e)}，已重置部分数据")
            # 仅重置有问题的时间数据，保留其他可能可用的数据
            if not isinstance(st.session_state.last_email_sent_time, datetime):
                st.session_state.last_email_sent_time = None
            if not st.session_state.next_scheduled_send or not isinstance(st.session_state.next_scheduled_send, datetime):
                st.session_state.next_scheduled_send = datetime.now()

def save_persistent_data():
    """将session_state中的关键数据保存到本地文件，增强验证"""
    try:
        # 验证时间是否有效
        if st.session_state.last_email_sent_time and not isinstance(st.session_state.last_email_sent_time, datetime):
            st.warning("发送时间格式错误，未保存")
            return
            
        data_to_save = {
            'patent_data': st.session_state.patent_data,
            'last_upload_time': st.session_state.last_upload_time,
            'reminder_sent': st.session_state.reminder_sent,
            'reminder_days': st.session_state.reminder_days,
            'last_email_sent_time': st.session_state.last_email_sent_time,
            'next_scheduled_send': st.session_state.next_scheduled_send
        }
        with open(DATA_FILE, 'wb') as f:
            pickle.dump(data_to_save, f)
    except Exception as e:
        st.error(f"保存数据失败：{str(e)}")

# 加载保存的邮箱配置
def load_email_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'rb') as f:
                config = pickle.load(f)
                st.session_state.email_config.update(config)
        except:
            st.warning("加载邮箱配置失败，使用默认配置")

# 保存邮箱配置
def save_email_config():
    try:
        with open(CONFIG_FILE, 'wb') as f:
            pickle.dump(st.session_state.email_config, f)
        st.success("邮箱配置已保存")
    except:
        st.error("保存邮箱配置失败")

# 邮件发送日志记录
def log_email_send(success, msg):
    """记录邮件发送日志"""
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f"[{datetime.now():%Y-%m-%d %H:%M}] 发送状态：{'成功' if success else '失败'}，信息：{msg}\n")
    except Exception as e:
        st.warning(f"日志记录失败：{str(e)}")

# 本地弹窗提醒组件
def local_notification(message, title="提醒"):
    st.markdown(
        f"""
        <div style="position: fixed; top: 20px; right: 20px; background-color: #fff; 
                    border-left: 4px solid #ffc107; padding: 15px; border-radius: 4px;
                    box-shadow: 0 4px 6px rgba(0,0,0,0.1); z-index: 1000;">
            <h3 style="margin-top: 0; color: #ffc107;">{title}</h3>
            <p>{message}</p>
        </div>
        """,
        unsafe_allow_html=True
    )

# 邮件发送功能
def send_email_reminder(sender_email, sender_password, smtp_server, smtp_port, 
                       receiver_email, patent_info):
    try:
        # 构建邮件内容
        subject = "专利缴费提醒"
        body = "以下专利即将到期或已过期，请及时处理：\n\n"
        for idx, patent in patent_info.iterrows():
            body += f"专利名称：{patent['专利名称']}\n"
            body += f"专利号：{patent['专利号']}\n"
            body += f"缴费截止日期：{patent['缴费截止日期'].strftime('%Y-%m-%d')}\n"
            body += f"距离到期天数：{patent['距离到期天数']}天\n"
            body += f"缴费金额：{patent['缴费金额']}元\n\n"

        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = sender_email
        msg['To'] = receiver_email
        msg['Date'] = formatdate()

        context = ssl.create_default_context()
        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context) as server:
                server.login(sender_email, sender_password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(smtp_server, smtp_port, timeout=10) as server:
                server.starttls(context=context)
                server.login(sender_email, sender_password)
                server.send_message(msg)

        return True, "邮件发送成功"
    except smtplib.SMTPAuthenticationError:
        return False, "认证失败：请检查邮箱账号或授权码是否正确"
    except smtplib.SMTPConnectError:
        return False, "连接失败：请检查SMTP服务器地址或端口是否正确"
    except Exception as e:
        return False, f"发送失败：{str(e)}"

# 自动发送提醒邮件的函数（添加了3 min间隔控制）
def auto_send_reminders():
    if st.session_state.patent_data is None:
        return False, "无专利数据可检查"
        
    # 获取配置
    cfg = st.session_state.email_config
    if not (cfg["email_enabled"] and cfg["sender_email"] and cfg["sender_password"] and cfg["receiver_email"]):
        return False, "邮箱配置不完整或未启用"
    
    # 初始化计划发送时间（首次运行或过期时）
    now = datetime.now()

    if not st.session_state.next_scheduled_send or st.session_state.next_scheduled_send <= now:
        # 计算下次发送时间（当前时间 + 3 min）
        st.session_state.next_scheduled_send = now + timedelta(minutes=3)
        save_persistent_data()  # 保存计划时间
    else:
        # 未到计划时间
        remaining = st.session_state.next_scheduled_send - now
        remaining_minutes = int(remaining.total_seconds() // 60)
        return False, f"未到发送时间，剩余 {remaining_minutes} 分钟"
    
    # 添加3 min发送间隔控制
    now = datetime.now()

    last_sent = st.session_state.last_email_sent_time
    if last_sent is not None:
        time_diff = now - last_sent
        if time_diff < timedelta(minutes=3):
            remaining_hours = int((timedelta(minutes=3) - time_diff).total_seconds() // 3600)
            return False, f"距离上次发送不足3 min，剩余{remaining_hours}分钟"
        
    # 处理数据
    df = st.session_state.patent_data.copy()
    today = datetime.today().date()
    df['距离到期天数'] = (df['缴费截止日期'] - pd.Timestamp(today)).dt.days
    df['状态'] = df['距离到期天数'].apply(
        lambda x: '已过期' if x < 0 else 
        '即将到期' if x <= st.session_state.reminder_days else 
        '正常'
    )
    
    # 检查需要提醒的专利
    reminder_patents = df[(df['状态'] == '即将到期') | (df['状态'] == '已过期')]
    if reminder_patents.empty:
        return True, "没有需要提醒的专利"
        
    # 发送邮件
    success, msg = send_email_reminder(
        cfg["sender_email"], cfg["sender_password"], 
        cfg["smtp_server"], cfg["smtp_port"],
        cfg["receiver_email"], reminder_patents
    )
    
    # 记录日志
    log_email_send(success, msg)
    
    # 如果发送成功，更新上次发送时间
    if success:
        st.session_state.last_email_sent_time = now
        # 确保下次发送时间正确更新
        st.session_state.next_scheduled_send = now + timedelta(minutes=3)
        save_persistent_data()
        
    return success, msg

# 标题
st.title("📅 专利缴费管理系统")
st.write("上传专利信息，系统将自动跟踪到期状态并提醒即将到期的项目")

# 显示正确的心跳接口地址（适配 Streamlit Cloud）
st.info(f"系统心跳接口：https://hszlxxts.streamlit.app/?heartbeat=1")

# 加载保存的配置（邮箱配置+核心数据）
load_email_config()
load_persistent_data()

# 侧边栏 - 设置
with st.sidebar:
    st.header("提醒设置")
    # 提醒提前天数（默认15天）
    reminder_days = st.slider("提前提醒天数", 7, 90, st.session_state.reminder_days)
    if reminder_days != st.session_state.reminder_days:
        st.session_state.reminder_days = reminder_days  # 更新会话状态
        save_persistent_data()  # 保存修改
    st.info(f"设置为提前 {reminder_days} 天提醒即将到期的专利")
    
    # 自动刷新设置
    st.subheader("自动刷新")
    st.session_state.auto_refresh = st.checkbox("启用页面自动刷新", value=True)
    # 缩短自动刷新间隔：支持1-60分钟（1小时），默认10分钟
    refresh_interval = st.slider(
        "刷新间隔（分钟）", 
        min_value=1, 
        max_value=60,  # 最大支持1小时
        value=2,      # 默认10分钟
        help="缩短了最大刷新间隔，现在最大为60分钟"
    )
    
    # 显示上次邮件发送时间
    if st.session_state.last_email_sent_time:
        st.info(f"上次邮件发送时间：{st.session_state.last_email_sent_time:%Y-%m-%d %H:%M}")
        next_send_time = st.session_state.last_email_sent_time + timedelta(minutes=3)
        if datetime.now() < next_send_time:
            st.info(f"下次邮件发送时间：{next_send_time:%Y-%m-%d %H:%M}")
    
    # 邮件提醒设置
    st.subheader("邮件提醒设置")
    with st.expander("配置邮件参数", expanded=False):
        # 使用会话状态中的配置值
        sender_email = st.text_input("发件人邮箱", value=st.session_state.email_config["sender_email"])
        sender_password = st.text_input("邮箱授权码", type="password", value=st.session_state.email_config["sender_password"])
        smtp_server = st.text_input("SMTP服务器", value=st.session_state.email_config["smtp_server"])
        smtp_port = st.number_input("SMTP端口", 0, 65535, value=st.session_state.email_config["smtp_port"])
        receiver_email = st.text_input("收件人邮箱", value=st.session_state.email_config["receiver_email"])
        email_enabled = st.checkbox("启用邮件提醒", value=st.session_state.email_config["email_enabled"])
        
        # 保存配置按钮
        if st.button("保存邮箱配置"):
            st.session_state.email_config.update({
                "sender_email": sender_email,
                "sender_password": sender_password,
                "smtp_server": smtp_server,
                "smtp_port": smtp_port,
                "receiver_email": receiver_email,
                "email_enabled": email_enabled
            })
            save_email_config()
    
    st.divider()
    st.info(f"上次数据上传时间：\n{st.session_state.last_upload_time}")
    if st.session_state.next_scheduled_send:
            now = datetime.now()
            if now < st.session_state.next_scheduled_send:
                remaining = st.session_state.next_scheduled_send - now
                remaining_hours = int(remaining.total_seconds() // 3600)
                remaining_minutes = int((remaining.total_seconds() % 3600) // 60)
                st.info(f"下次计划发送时间：{st.session_state.next_scheduled_send:%Y-%m-%d %H:%M}")
                st.info(f"距离下次发送还有：{remaining_hours}小时{remaining_minutes}分钟")
            else:
                st.info("即将检查并发送提醒邮件...")

# 上传Excel文件
st.subheader("上传专利数据")
uploaded_file = st.file_uploader(
    "上传Excel文件（需包含列：专利名称、专利号、缴费截止日期、缴费金额）",
    type=["xlsx", "xls"]
)

if uploaded_file is not None:
    try:
        df = pd.read_excel(uploaded_file)
        required_columns = ['专利名称', '专利号', '缴费截止日期', '缴费金额']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            st.error(f"Excel文件缺少必要的列：{', '.join(missing_columns)}")
        else:
            df['专利号'] = df['专利号'].astype(str)
            df['缴费截止日期'] = pd.to_datetime(df['缴费截止日期'])
            st.session_state.patent_data = df
            st.session_state.last_upload_time = datetime.now().strftime('%Y-%m-%d %H:%M')
            save_persistent_data()  # 上传成功后保存数据
            st.success("文件上传成功并已保存！")
    except Exception as e:
        st.error(f"文件处理失败：{str(e)}")

# 显示已保存的专利数据
if st.session_state.patent_data is not None:
    df = st.session_state.patent_data.copy()
    today = datetime.today().date()
    df['距离到期天数'] = (df['缴费截止日期'] - pd.Timestamp(today)).dt.days
    df['状态'] = df['距离到期天数'].apply(
        lambda x: '已过期' if x < 0 else 
        '即将到期' if x <= st.session_state.reminder_days else 
        '正常'
    )
    
    reminder_patents = df[(df['状态'] == '即将到期') | (df['状态'] == '已过期')]
    if not reminder_patents.empty:
        patent_ids = [f"{row['专利号']}_{row['缴费截止日期'].strftime('%Y%m%d')}" 
                     for _, row in reminder_patents.iterrows()]
        
        new_reminders = [pid for pid in patent_ids if pid not in st.session_state.reminder_sent]
        if new_reminders:
            reminder_count = len(new_reminders)
            local_notification(
                f"发现 {reminder_count} 项需要关注的专利，请及时处理！",
                "⚠️ 专利缴费提醒"
            )
            for pid in new_reminders:
                st.session_state.reminder_sent.add(pid)
            save_persistent_data()  # 提醒记录更新后保存数据
    
    # 显示所有专利信息
    st.subheader("所有专利信息")
    def highlight_status(row):
        if row['状态'] == '即将到期':
            return ['background-color: #fff3cd'] * len(row)
        elif row['状态'] == '已过期':
            return ['background-color: #f8d7da'] * len(row)
        else:
            return [''] * len(row)
    
    styled_df = df.style.apply(highlight_status, axis=1)
    st.dataframe(styled_df, use_container_width=True)
    
    # 显示需要关注的专利
    upcoming = df[(df['状态'] == '即将到期') | (df['状态'] == '已过期')]
    if not upcoming.empty:
        st.subheader("⚠️ 需要关注的专利")
        st.dataframe(upcoming, use_container_width=True)
    else:
        st.success("没有即将到期或已过期的专利，一切正常！")
    
    # 数据可视化
    st.subheader("专利状态分布")
    status_counts = df['状态'].value_counts()
    st.bar_chart(status_counts)
    
    # 即将到期专利的倒计时展示
    if not df[df['状态'] == '即将到期'].empty:
        st.subheader("📌 即将到期专利倒计时")
        countdown_df = df[df['状态'] == '即将到期'][['专利名称', '专利号', '缴费截止日期', '距离到期天数']]
        countdown_df = countdown_df.sort_values('距离到期天数')
        st.dataframe(countdown_df, use_container_width=True)

else:
    st.info("请上传专利数据Excel文件，上传后会自动保存")
    
    # 提供模板下载
    sample_data = {
        '专利名称': ['发明专利A', '实用新型专利B', '外观设计专利C'],
        '专利号': ['ZL202010000000', 'ZL202020000000', 'ZL202030000000'],
        '缴费截止日期': [
            (datetime.today() + timedelta(days=15)).strftime('%Y-%m-%d'),
            (datetime.today() + timedelta(days=45)).strftime('%Y-%m-%d'),
            (datetime.today() - timedelta(days=5)).strftime('%Y-%m-%d')
        ],
        '缴费金额': [1300, 900, 500]
    }
    sample_df = pd.DataFrame(sample_data)
    buffer = BytesIO()
    sample_df.to_excel(buffer, index=False)
    buffer.seek(0)
    st.download_button(
        label="下载示例Excel模板",
        data=buffer,
        file_name="专利缴费信息模板.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# 自动刷新功能和邮件检查
if st.session_state.auto_refresh:
    refresh_js = f"""
    <script>
        // 检查是否是首次加载（用localStorage标记）
        if (!localStorage.getItem('hasRefreshedOnce')) {{
            // 首次加载：立即刷新
            window.location.reload();
            localStorage.setItem('hasRefreshedOnce', 'true');
        }} else {{
            // 非首次加载：按间隔刷新
            setTimeout(function() {{
                window.location.reload();
            }}, {refresh_interval * 60 * 1000});
        }}
    </script>
    """
    st.markdown(refresh_js, unsafe_allow_html=True)
    st.caption(f"页面将在 {refresh_interval} 分钟后自动刷新")
    
    # 仅在自动刷新时检查邮件（非首次启动）
    if not st.session_state.is_first_load and st.session_state.email_config["email_enabled"]:
        st.spinner("自动刷新：检查邮件提醒...")  # 仅显示状态，不阻塞
        
        # 独立线程执行，避免阻塞页面
        def check_and_send():
            time_module.sleep(5)  # 延迟确保页面加载
            result, msg = auto_send_reminders()
            # 线程内无法直接更新UI，可通过日志记录结果
            log_email_send(result, f"线程检查结果：{msg}")
        
        threading.Thread(target=check_and_send, daemon=True).start()
    else:
        # 首次加载时显示状态信息
        if st.session_state.email_config["email_enabled"]:
            now = datetime.now()
            last_sent = st.session_state.last_email_sent_time
            if last_sent is None:
                st.info("邮件提醒功能已启用，将在首次自动刷新时检查发送")
            else:
                time_diff = now - last_sent
                if time_diff < timedelta(minutes=3):
                    remaining_seconds = (timedelta(minutes=3) - time_diff).total_seconds()
                    remaining_hours = int(remaining_seconds // 3600)
                    remaining_minutes = int((remaining_seconds % 3600) // 60)
                    st.info(f"邮件提醒功能已启用，距离下次发送还有{remaining_hours}小时{remaining_minutes}分钟")


# 标记为非首次加载
if st.session_state.is_first_load:
    st.session_state.is_first_load = False