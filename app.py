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
import smtplib
from smtplib import SMTPException

# 页面配置
st.set_page_config(
    page_title="专利缴费管理系统",
    page_icon="📅",
    layout="wide"
)

# 初始化会话状态（持久化存储数据）
if 'patent_data' not in st.session_state:
    st.session_state.patent_data = None  # 存储上传的专利数据
if 'last_upload_time' not in st.session_state:
    st.session_state.last_upload_time = "无"  # 记录上次上传时间
if 'reminder_sent' not in st.session_state:
    st.session_state.reminder_sent = set()  # 记录已发送提醒的专利ID
if 'auto_refresh' not in st.session_state:
    st.session_state.auto_refresh = True  # 自动刷新开关

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

        # 连接服务器（587端口需用TLS加密）
        context = ssl.create_default_context()  # 安全上下文
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls(context=context)  # 启用TLS加密（关键步骤）
            server.login(sender_email, sender_password)  # 登录（password为授权码）
            server.send_message(msg)  # 发送邮件

        return True, "邮件发送成功"
    except smtplib.SMTPAuthenticationError:
        return False, "认证失败：请检查邮箱账号或授权码是否正确"
    except smtplib.SMTPConnectError:
        return False, "连接失败：请检查SMTP服务器地址或端口是否正确"
    except Exception as e:
        return False, f"发送失败：{str(e)}"

# 标题
st.title("📅 专利缴费管理系统")
st.write("上传专利信息，系统将自动跟踪到期状态并提醒即将到期的项目")

# 侧边栏 - 设置
with st.sidebar:
    st.header("提醒设置")
    # 提醒提前天数（默认15天）
    reminder_days = st.slider("提前提醒天数", 7, 90, 15)
    st.info(f"设置为提前 {reminder_days} 天提醒即将到期的专利")
    
    # 自动刷新设置
    st.subheader("自动刷新")
    st.session_state.auto_refresh = st.checkbox("启用页面自动刷新", value=True)
    refresh_interval = st.slider("刷新间隔（分钟）", 1, 60, 10)
    
    # 邮件提醒设置
    st.subheader("邮件提醒设置")
    with st.expander("配置邮件参数", expanded=False):
        sender_email = st.text_input("发件人邮箱")
        sender_password = st.text_input("邮箱授权码", type="password")
        smtp_server = st.text_input("SMTP服务器", "smtp.qq.com")
        smtp_port = st.number_input("SMTP端口", 0, 65535, 587)
        receiver_email = st.text_input("收件人邮箱")
        email_enabled = st.checkbox("启用邮件提醒")
    
    st.divider()
    st.info(f"上次数据上传时间：\n{st.session_state.last_upload_time}")

    try:
        server = smtplib.SMTP('smtp.example.com', 587)
        server.starttls()
        server.login('your_email', 'your_password')
        # 发送邮件代码
        server.quit()
    except SMTPException as e:
        print(f"发送失败：{str(e)}")  # 打印具体错误信息
# 上传Excel文件（覆盖旧数据）
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
            # 处理日期格式
            df['缴费截止日期'] = pd.to_datetime(df['缴费截止日期'])
            # 保存数据到会话状态（持久化）
            st.session_state.patent_data = df
            st.session_state.last_upload_time = datetime.now().strftime('%Y-%m-%d %H:%M')
            st.success("文件上传成功并已保存！")
    except Exception as e:
        st.error(f"文件处理失败：{str(e)}")

# 显示已保存的专利数据
if st.session_state.patent_data is not None:
    # 处理数据并添加状态列
    df = st.session_state.patent_data.copy()
    today = datetime.today().date()
    df['距离到期天数'] = (df['缴费截止日期'] - pd.Timestamp(today)).dt.days
    df['状态'] = df['距离到期天数'].apply(
        lambda x: '已过期' if x < 0 else 
        '即将到期' if x <= reminder_days else 
        '正常'
    )
    
    # 检查需要提醒的专利并显示本地弹窗
    reminder_patents = df[(df['状态'] == '即将到期') | (df['状态'] == '已过期')]
    if not reminder_patents.empty:
        # 生成唯一标识（专利号+日期，避免重复提醒）
        patent_ids = [f"{row['专利号']}_{row['缴费截止日期'].strftime('%Y%m%d')}" 
                     for _, row in reminder_patents.iterrows()]
        
        # 显示本地弹窗（只显示新的提醒）
        new_reminders = [pid for pid in patent_ids if pid not in st.session_state.reminder_sent]
        if new_reminders:
            reminder_count = len(new_reminders)
            local_notification(
                f"发现 {reminder_count} 项需要关注的专利，请及时处理！",
                "⚠️ 专利缴费提醒"
            )
            # 更新已提醒记录
            for pid in new_reminders:
                st.session_state.reminder_sent.add(pid)
        
        # 发送邮件提醒（如果配置了邮件且启用）
        if email_enabled and sender_email and sender_password and receiver_email:
            email_result, email_msg = send_email_reminder(
                sender_email, sender_password, smtp_server, smtp_port,
                receiver_email, reminder_patents
            )
            if email_result:
                st.success("邮件提醒已发送")
            else:
                st.warning(f"邮件提醒发送失败：{email_msg}")
    
    # 显示所有专利信息
    st.subheader("所有专利信息")
    # 添加颜色标记（即将到期标黄，已过期标红）
    def highlight_status(row):
        if row['状态'] == '即将到期':
            return ['background-color: #fff3cd'] * len(row)
        elif row['状态'] == '已过期':
            return ['background-color: #f8d7da'] * len(row)
        else:
            return [''] * len(row)
    
    styled_df = df.style.apply(highlight_status, axis=1)
    st.dataframe(styled_df, use_container_width=True)
    
    # 显示需要关注的专利（即将到期和已过期）
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
    # 未上传数据时显示提示和模板
    st.info("请上传专利数据Excel文件，上传后会自动保存")
    
    # 提供模板下载
    sample_data = {
        '专利名称': ['发明专利A', '实用新型专利B', '外观设计专利C'],
        '专利号': ['ZL202010000000.0', 'ZL202020000000.0', 'ZL202030000000.0'],
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

# 自动刷新功能
if st.session_state.auto_refresh:
    st.markdown(
        f"""
        <script>
        setTimeout(function() {{
            window.location.reload();
        }}, {refresh_interval * 60 * 1000});  // 毫秒为单位
        </script>
        """,
        unsafe_allow_html=True
    )
    st.caption(f"页面将在 {refresh_interval} 分钟后自动刷新")