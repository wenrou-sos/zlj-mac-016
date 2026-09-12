# 大棚种植管理系统

记录大棚温湿度、光照与灌溉情况，安排施肥/浇水/采收任务，环境异常时自动告警提醒工作人员。

## 技术栈

- **后端**：FastAPI + SQLite（含本地传感器数据模拟器，每 10 秒采集一轮）
- **前端**：Vue 3（已本地化到 `frontend/static/`，无需联网、无需构建）

## 启动

```bash
pip install fastapi "uvicorn[standard]"
./run.sh          # 或 cd backend && python3 -m uvicorn main:app --port 8000
```

浏览器访问 http://localhost:8000

## 功能

| 模块 | 说明 |
|------|------|
| 环境概览 | 各大棚实时温度/湿度/光照/土壤湿度卡片，越限标红；历史趋势折线图 |
| 大棚管理 | 概览页「⚙ 大棚管理」：新增大棚、修改名称/作物、停用/启用；停用后不再采集和告警，历史读数、任务、告警仍可查（历史图表中标注"已停用"） |
| 任务管理 | 安排施肥、浇水、采收任务，支持完成/取消 |
| 灌溉记录 | 记录灌溉量、方式（滴灌/喷灌/漫灌） |
| 告警中心 | 传感器越限自动生成告警（警告/严重两级），恢复后自动解除；处理时可登记处理人和处理备注，已处理的告警也可补记 |
| 外部通知 | 新告警产生时推送到 Webhook 和/或邮件（SMTP），在告警中心顶部配置；同一轮越限只推送一次，恢复后再次越限才重新推送；未配置或推送失败不影响告警生成与解除，送达状态（已推送/推送失败/未推送）显示在告警记录中 |

## 外部通知配置

在「告警中心」顶部展开配置面板，或编辑 `backend/notify_config.json`：

```json
{
  "webhook_url": "https://example.com/hook",
  "smtp": {
    "host": "smtp.example.com", "port": 465,
    "username": "alert@example.com", "password": "xxx",
    "sender": "alert@example.com",
    "recipients": "staff1@example.com,staff2@example.com",
    "use_tls": true
  }
}
```

- Webhook：POST JSON，含大棚、指标、当前值、级别、时间等字段
- 邮件：SMTP_SSL（use_tls=false 时使用 STARTTLS）
- 两个渠道可同时启用，任一送达即视为已推送
- `POST /api/notify/test` 可发送测试通知验证配置

## 告警阈值（`backend/simulator.py` 中 `THRESHOLDS` 可调）

- 温度 15~32 ℃
- 空气湿度 40%~85%
- 土壤湿度 20%~60%
- 光照 2000~80000 lux（仅白天 6:00–20:00 检查）

模拟器约 3% 概率产生异常数据，便于演示告警流程。

## 目录结构

```
greenhouse/
├── backend/
│   ├── main.py        # FastAPI 应用与 API 路由
│   ├── database.py    # SQLite 建表与连接
│   ├── simulator.py   # 传感器模拟 + 阈值告警 + 触发外部推送
│   ├── notifier.py    # Webhook / 邮件通知渠道
│   ├── notify_config.json  # 通知渠道配置（页面保存后生成）
│   └── greenhouse.db  # 数据库文件（首次运行自动创建）
├── frontend/
│   ├── index.html     # Vue 单页应用
│   └── static/vue.global.prod.js
└── run.sh
```

## 主要 API

- `GET/POST /api/greenhouses`，`PATCH /api/greenhouses/{id}` 大棚新增/改名/启停
- `GET /api/sensors/latest` 各大棚最新读数
- `GET /api/sensors/history?greenhouse_id=1&limit=60` 历史数据
- `GET/POST /api/tasks`，`PATCH /api/tasks/{id}` 任务管理
- `GET/POST /api/irrigation` 灌溉记录
- `GET /api/alerts`，`POST /api/alerts/{id}/resolve`（可带处理人/备注），`PATCH /api/alerts/{id}/handle` 补记
- `GET/PUT /api/notify/config`，`POST /api/notify/test` 通知渠道
- `GET /api/dashboard` 概览统计
