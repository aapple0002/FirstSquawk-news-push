import feedparser
import requests
import smtplib
from email.mime.text import MIMEText
import os
import re
import datetime
from datetime import timezone, timedelta

# ---------------------- Gmail配置（从GitHub Secret读取） ----------------------
GMAIL_EMAIL = os.getenv("GMAIL_EMAIL")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
RECEIVER_EMAILS = os.getenv("RECEIVER_EMAILS")
SMTP_SERVER = "smtp.gmail.com"
CUSTOM_NICKNAME = "📩全球快讯"

# ---------------------- 固定配置 ----------------------
RSS_URL = "https://rss.xcancel.com/FirstSquawk/rss"
LAST_LINK_FILE = "last_link.txt"
# 每次最多推送前100条新内容
MAX_PUSH_COUNT = 100

# ===================== 时间格式化（保留原逻辑） =====================
def get_show_time(news):
    beijing_tz = timezone(timedelta(hours=8))
    pub_date_str = news.get("pubdate", news.get("published", "")).strip()
    
    if pub_date_str:
        try:
            dt_formats = [
                "%a, %d %b %Y %H:%M:%S GMT",
                "%a, %d %b %Y %H:%M:%S %z",
                "%a, %d %b %Y %H:%M %z",
                "%d %b %Y %H:%M:%S %z",
                "%Y-%m-%d %H:%M:%S %z"
            ]
            for fmt in dt_formats:
                try:
                    dt = datetime.datetime.strptime(pub_date_str, fmt)
                    if dt.tzinfo is None:
                        dt_utc = dt.replace(tzinfo=timezone.utc)
                    else:
                        dt_utc = dt.astimezone(timezone.utc)
                    dt_beijing = dt_utc.astimezone(beijing_tz)
                    return dt_beijing.strftime("%Y-%m-%d %H:%M")
                except:
                    continue
        except:
            pass

    current_bj = datetime.datetime.now(beijing_tz)
    return current_bj.strftime("%Y-%m-%d %H:%M")

# ===================== 内容解析（保留原逻辑） =====================
def parse_news_type_and_content(news):
    raw_title = news.get("title", "").strip()
    no_title_flags = ["[No Title]", "no title", "untitled", "- Post from "]
    is_forward = not raw_title or any(flag in raw_title for flag in no_title_flags)
    forward_tag = "（图片或转发）" if is_forward else ""

    if is_forward:
        content = news.get("content", [{}])[0].get("value", "") if news.get("content") else ""
        clean_text = re.sub(r'<.*?>', '', content, flags=re.DOTALL)
        clean_text = re.sub(r'https?://\S+', '', clean_text).strip()
        clean_text = re.sub(r'^(\s*RT[:\s]*|\s*@\w+:)', '', clean_text, flags=re.IGNORECASE)
        trump_text = clean_text.strip() if clean_text and len(clean_text) > 2 else "无文字描述"
        content_text = f"【快讯】：{trump_text}"
    else:
        clean_title = re.sub(r'https?://\S+', '', raw_title).strip()
        content_text = f"【快讯】：{clean_title}"

    return forward_tag, content_text

# ===================== 核心修复：带浏览器请求头抓取RSS（解决400错误） =====================
def fetch_news():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/rss+xml,application/xml,*/*;q=0.9",
        "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive"
    }
    try:
        response = requests.get(RSS_URL, headers=headers, timeout=20)
        response.raise_for_status()
        feed = feedparser.parse(response.content)
        if not feed.entries:
            print("📭 未抓取到任何资讯")
            return [], None
        # 取前MAX_PUSH_COUNT条（默认100条）
        news_list = feed.entries[:MAX_PUSH_COUNT]
        latest_link = news_list[0]["link"].strip() if news_list else None
        return news_list, latest_link
    except requests.exceptions.RequestException as e:
        print(f"❌ 资讯抓取失败：{str(e)}")
        return [], None

# ===================== 持久化：加载/保存最后一条链接 =====================
def load_last_link():
    if os.path.exists(LAST_LINK_FILE):
        with open(LAST_LINK_FILE, 'r', encoding='utf-8') as f:
            return f.read().strip()
    return None

def save_last_link(link):
    with open(LAST_LINK_FILE, 'w', encoding='utf-8') as f:
        f.write(link)

# ===================== 生成多快讯邮件HTML（支持批量推送） =====================
def make_email_content(news_list):
    if not news_list:
        return "<p style='font-size:16px; color:#FFFFFF;'>暂无可用的资讯</p>"
    
    # 样式配置（沿用你原设计）
    title_color = "#C8102E"
    time_color = "#1E90FF"
    serial_color = "#FFFFFF"
    forward_color = "#C8102E"
    content_color = "#FFFFFF"
    link_color = "#1E90FF"
    arrow_color = "#FFCC00"
    
    content_indent = "20px"
    card_margin = "0 0 4px 0"
    card_padding = "6px"
    line_margin = "0 0 4px 0"

    email_title_html = f"""
    <p style='margin: 0 0 8px 0; padding: 6px; background-color:#2D2D2D; border-left:4px solid {title_color};'>
        <strong><span style='color:{title_color}; font-size:18px;'>♥️ 「7*24全球速递」</span></strong>
    </p>
    """

    news_items = []
    for i, news in enumerate(news_list, 1):
        news_link = news["link"]
        show_time = get_show_time(news)
        forward_tag, content_text = parse_news_type_and_content(news)
        
        news_items.append(f"""
        <div style='margin:{card_margin}; padding:{card_padding}; background-color:#2D2D2D; border-radius:4px;'>
            <div style='display: flex; align-items: center; margin:{line_margin};'>
                <span style='color:{serial_color}; font-size:15px; font-weight:bold; margin-right: 8px;'>{i}.</span>
                <div style='flex: 1;'>
                    <span style='color:{time_color}; font-weight:bold; font-size:15px;'>【{show_time}】</span>
                    <span style='color:{forward_color}; font-weight:bold; margin:0 1px; font-size:15px;'>{forward_tag}</span>
                </div>
            </div>
            <p style='margin:{line_margin}; padding:0 0 0 {content_indent}; line-height:1.4; font-size:16px; color:{content_color}; margin-top:0;'>
                {content_text}
            </p>
            <p style='margin:0; padding:0 0 0 {content_indent}; line-height:1.4; font-size:14px;'>
                <span style='color:{arrow_color}; font-size:16px;'>👉</span>
                <a href='{news_link}' target='_blank' style='color:{link_color}; text-decoration:none;'>查看原文</a>
            </p>
        </div>
        """)
    return email_title_html + "".join(news_items)

# ===================== 发送邮件 =====================
def send_email(html_content):
    if not all([GMAIL_EMAIL, GMAIL_APP_PASSWORD, RECEIVER_EMAILS]):
        print("❌ 请先配置GMAIL_EMAIL、GMAIL_APP_PASSWORD、RECEIVER_EMAILS这3个Secret！")
        return
    receivers = [email.strip() for email in RECEIVER_EMAILS.split(",") if email.strip()]
    if not receivers:
        print("❌ 收件人邮箱格式错误（多邮箱用英文逗号分隔）")
        return

    try:
        smtp = smtplib.SMTP_SSL(SMTP_SERVER, 465, timeout=20)
        smtp.login(GMAIL_EMAIL, GMAIL_APP_PASSWORD)
        print(f"✅ Gmail连接成功，即将向{len(receivers)}个收件人发送资讯邮件")

        current_bj_time = datetime.datetime.now(timezone(timedelta(hours=8)))
        bj_date = current_bj_time.strftime("%Y-%m-%d")
        subject = f"⏰ FirstSquawk 实时快讯 | {bj_date}（批量推送）"

        for receiver in receivers:
            msg = MIMEText(html_content, "html", "utf-8")
            msg["From"] = f"{CUSTOM_NICKNAME} <{GMAIL_EMAIL}>"
            msg["To"] = receiver
            msg["Subject"] = subject
            smtp.sendmail(GMAIL_EMAIL, [receiver], msg.as_string())
            print(f"✅ 已发送给：{receiver}")

        smtp.quit()
        print("✅ 所有邮件发送完成！")
    except smtplib.SMTPAuthenticationError:
        print("""❌ Gmail登录失败！请检查：
        1. Secrets里的邮箱/应用密码是否正确；
        2. Gmail是否开启「两步验证」；
        3. 应用专用密码是否有效（重新生成试试）。""")
    except Exception as e:
        print(f"❌ 邮件发送失败：{str(e)}")
        raise

# ===================== 程序入口（核心修改：批量推送前100条新内容） =====================
if __name__ == "__main__":
    utc_now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    cst_now = datetime.datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    print(f"==================================================")
    print(f"📅 执行时间 | UTC：{utc_now} | 北京时间：{cst_now}")
    print(f"📡 订阅源 | {RSS_URL} | 单次最多推送：{MAX_PUSH_COUNT}条")
    print(f"==================================================")

    try:
        news_list, latest_link = fetch_news()
        if not news_list:
            print("🎉 本次推送流程结束（无新资讯或抓取失败）")
            exit()

        last_link = load_last_link()
        new_news = []

        if last_link is None:
            # 首次运行：直接推送前100条
            new_news = news_list
        else:
            # 遍历新闻列表，收集所有「比上次新」的内容（RSS倒序，直到遇到last_link为止）
            for news in news_list:
                link = news["link"].strip()
                if link == last_link:
                    break
                new_news.append(news)
            # 反转顺序：让邮件里按「旧→新」排列，更易读
            new_news = new_news[::-1]

        if new_news:
            print(f"🚨 检测到 {len(new_news)} 条新资讯，准备推送！")
            email_html = make_email_content(new_news)
            send_email(email_html)
            # 保存最新一条的链接，避免下次重复推送
            save_last_link(latest_link)
        else:
            print("ℹ️  无新资讯，本次跳过推送")
        print("🎉 本次推送流程结束")
    except Exception as e:
        print(f"💥 程序异常：{str(e)}")
        raise
