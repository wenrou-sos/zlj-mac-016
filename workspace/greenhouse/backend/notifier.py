"""外部通知渠道：Webhook / 邮件推送。

设计原则：任何推送失败都只返回状态、绝不抛异常，
不影响告警的生成与自动解除主流程。
"""
import json
import smtplib
import urllib.request
from email.header import Header
from email.mime.text import MIMEText
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "notify_config.json"

DEFAULT_CONFIG = {
    "webhook_url": "",
    "smtp": {
        "host": "",
        "port": 465,
        "username": "",
        "password": "",
        "sender": "",
        "recipients": "",   # 多个收件人用英文逗号分隔
        "use_tls": True,
    },
}

LEVEL_NAMES = {"warning": "警告", "critical": "严重"}


def load_config() -> dict:
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))  # 深拷贝
    if CONFIG_PATH.exists():
        try:
            saved = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            cfg["webhook_url"] = saved.get("webhook_url", "")
            cfg["smtp"].update(saved.get("smtp", {}))
        except (json.JSONDecodeError, OSError):
            pass
    return cfg


def save_config(cfg: dict):
    CONFIG_PATH.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def build_alert_text(alert: dict) -> str:
    """告警通知正文：大棚、指标、当前值、发生时间"""
    return (
        f"【大棚告警】{alert['greenhouse_name']} 发生{LEVEL_NAMES.get(alert['level'], alert['level'])}告警\n"
        f"指标：{alert['metric_name']}\n"
        f"当前值：{alert['value']}{alert['unit']}\n"
        f"详情：{alert['message']}\n"
        f"时间：{alert['created_at']}"
    )


def _post_webhook(url: str, alert: dict, text: str) -> str | None:
    """POST JSON 到 webhook，返回 None 表示成功，否则返回错误描述"""
    payload = {
        "type": "greenhouse_alert",
        "level": alert["level"],
        "greenhouse": alert["greenhouse_name"],
        "metric": alert["metric_name"],
        "value": alert["value"],
        "unit": alert["unit"],
        "message": alert["message"],
        "time": alert["created_at"],
        "text": text,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status >= 400:
                return f"webhook 返回 HTTP {resp.status}"
        return None
    except Exception as e:
        return f"webhook 推送失败：{e}"


def _send_email(smtp: dict, subject: str, text: str) -> str | None:
    """发送邮件，返回 None 表示成功，否则返回错误描述"""
    recipients = [r.strip() for r in smtp.get("recipients", "").split(",") if r.strip()]
    if not recipients:
        return "未配置收件人"
    msg = MIMEText(text, "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = smtp.get("sender") or smtp.get("username", "")
    msg["To"] = ", ".join(recipients)
    try:
        if smtp.get("use_tls", True):
            server = smtplib.SMTP_SSL(smtp["host"], int(smtp.get("port", 465)), timeout=8)
        else:
            server = smtplib.SMTP(smtp["host"], int(smtp.get("port", 25)), timeout=8)
            server.starttls()
        with server:
            if smtp.get("username"):
                server.login(smtp["username"], smtp.get("password", ""))
            server.sendmail(msg["From"], recipients, msg.as_string())
        return None
    except Exception as e:
        return f"邮件发送失败：{e}"


def send_alert_notification(alert: dict) -> tuple[str, str]:
    """向所有已配置渠道推送告警。

    返回 (status, error)：
    - sent   至少一个渠道送达（error 中可能附带部分渠道失败信息）
    - failed 有配置渠道但全部失败
    - none   未配置任何外部渠道
    """
    cfg = load_config()
    text = build_alert_text(alert)
    errors: list[str] = []
    attempted = 0

    if cfg.get("webhook_url"):
        attempted += 1
        err = _post_webhook(cfg["webhook_url"], alert, text)
        if err:
            errors.append(err)

    smtp = cfg.get("smtp", {})
    if smtp.get("host") and smtp.get("recipients"):
        attempted += 1
        err = _send_email(smtp, f"【大棚告警】{alert['greenhouse_name']} {alert['metric_name']}异常", text)
        if err:
            errors.append(err)

    if attempted == 0:
        return "none", "未配置外部通知渠道"
    if len(errors) == attempted:
        return "failed", "；".join(errors)
    return "sent", "；".join(errors)
