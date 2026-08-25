import smtplib
from email.mime.text import MIMEText
import requests


def send_pushplus(token: str, title: str, content: str) -> bool:
    try:
        resp = requests.post(
            'http://www.pushplus.plus/send',
            json={'token': token, 'title': title, 'content': content, 'template': 'html'},
            timeout=10,
        )
        return resp.status_code == 200
    except Exception:
        return False


def send_email(smtp_cfg: dict, to: str, subject: str, body: str) -> bool:
    try:
        msg = MIMEText(body, 'html', 'utf-8')
        msg['Subject'] = subject
        msg['From'] = smtp_cfg['from']
        msg['To'] = to

        with smtplib.SMTP(smtp_cfg['host'], smtp_cfg['port'], timeout=10) as srv:
            srv.starttls()
            srv.login(smtp_cfg['user'], smtp_cfg['pass'])
            srv.sendmail(smtp_cfg['from'], [to], msg.as_string())
        return True
    except Exception:
        return False


def notify_new_assets(user, domain: str, new_subs: list):
    if not new_subs:
        return

    count = len(new_subs)
    preview = '<br>'.join(new_subs[:20])
    more = f'<br>... 及其他 {count - 20} 个资产' if count > 20 else ''

    title = f'[AssetMonitor] {domain} +{count} 新资产'
    body = (
        f'<h3>🔍 新资产通知</h3>'
        f'<p>域名: <b>{domain}</b></p>'
        f'<p>新发现: <b>{count}</b> 个子域</p>'
        f'<hr><pre>{preview}{more}</pre><hr>'
        f'<small>Asset Monitor System</small>'
    )

    if user.notify_wechat and user.pushplus_token:
        send_pushplus(user.pushplus_token, title, body)

    if user.notify_email and user.email and user.smtp_host:
        send_email(
            {
                'host': user.smtp_host,
                'port': user.smtp_port,
                'user': user.smtp_user,
                'pass': user.smtp_pass,
                'from': user.smtp_from,
            },
            user.email,
            title,
            body,
        )
