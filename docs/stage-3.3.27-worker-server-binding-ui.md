# Stage 3.3.27 Worker Server Binding UI

## 本阶段目标

本阶段解决 Worker 已注册在线但“落地服务器 / 中转服务器”页面仍为空的问题：添加服务器时先创建本地服务器资源记录，再生成绑定该资源记录的 Worker 安装命令。Worker 注册和心跳后，资源记录可在 UI 中显示为在线。

## 当前问题

- Worker 注册写入 `workers` 表。
- 落地服务器页面读取 `vps_servers` 表。
- 中转服务器页面读取 `transit_resources` 表。
- 如果 token 未绑定服务器资源，UI 无法知道在线 Worker 属于哪一条服务器记录。

## 新主流程

### 落地服务器

1. 用户在“落地服务器”页面填写服务器名称、服务器 IP、过期时间。
2. 前端调用 `POST /api/vps/worker-bootstrap`。
3. 后端创建 `vps_servers` 记录，状态为 `pending_worker`。
4. 后端创建 `role=landing` 的一次性 Worker token，并将 `worker_tokens.server_id` 绑定到 `vps_servers.id`。
5. 前端显示安装命令。
6. Worker 注册成功后，`workers.server_id` 精准绑定到 `vps_servers.id`。
7. Heartbeat 正常后，资源状态显示在线。

### 中转服务器

1. 用户在“中转服务器”页面填写中转服务器名称、IP、过期时间。
2. 前端调用 `POST /api/transit-resources/worker-bootstrap`。
3. 后端创建 `transit_resources` 记录，状态为 `pending_worker`。
4. 后端创建 `role=transit` 的一次性 Worker token，并将 `worker_tokens.server_id` 绑定到 `transit_resources.id`。
5. 前端显示安装命令。
6. Worker 注册成功后，`workers.server_id` 精准绑定到 `transit_resources.id`。
7. Heartbeat 正常后，资源状态显示在线。

## 状态定义

- `pending_worker` / 待接入：资源记录已创建，Worker 尚未注册或尚未心跳。
- `online` / 在线：Worker 最近心跳正常。
- `offline` / 离线：Worker 曾注册过，但心跳超时。
- `unchecked` / 未检测：兼容旧 SSH 数据或没有 Worker / SSH 状态来源。

## Worker 绑定规则

- `landing` token 只能绑定 `vps_servers.id`。
- `transit` token 只能绑定 `transit_resources.id`。
- Worker 注册时校验 token、role、过期状态和绑定目标。
- 注册成功后只保存 `worker_secret_hash`，`worker_secret` 只返回一次。
- Heartbeat 正常更新 Worker 状态，并同步对应资源状态。
- 对历史未绑定 Worker，heartbeat 时仅在 `public_ip` 能唯一匹配资源记录时补绑定；不能唯一确认时不写假绑定。

## API 返回增强

`GET /api/vps` 和 `GET /api/transit-resources` 增加：

- `connection_mode`
- `worker_id`
- `worker_status`
- `worker_role`
- `worker_hostname`
- `worker_interface_name`
- `worker_version`
- `worker_last_heartbeat_at`
- `worker_online`
- `display_status`

接口不返回 token、token_hash、worker_secret、worker_secret_hash、完整敏感配置或完整节点链接。

## UI 展示规则

- 添加落地服务器 / 中转服务器默认显示 Worker 安装命令流程。
- 保存服务器后立即显示“待接入”记录。
- 在线 Worker 服务器允许后续本地 UI 入口继续操作。
- Worker 未在线时禁止添加节点。
- 安装命令支持 Clipboard API，并在 HTTP 页面受限时 fallback 到选中 textarea 复制。
- 复制失败时提示用户手动按 `Ctrl+A / Ctrl+C`，Mac 使用 `Command+A / Command+C`。

## docker-compose 修复

- `frontend` build 阶段通过 build args 传入 `NEXT_PUBLIC_API_BASE_URL`。
- `backend` / `worker` 容器透传 `ADMIN_USERNAME` 和 `ADMIN_PASSWORD_HASH`。
- 未修改默认端口。
- 未写入真实密码、真实 hash 或真实 token。

## Migration 结论

本阶段未新增 migration。现有表已经具备必要字段：

- `worker_tokens.server_id`
- `workers.server_id`
- `vps_servers.status`
- `transit_resources.status`

## 安全边界

- 未执行 SSH / 远程命令。
- 未自动安装 Worker 到真实 VPS。
- 未创建节点。
- 未创建中转链路。
- 未新增监听端口。
- 未修改 Xray。
- 未修改 socat / gost。
- 未修改 `node.share_link`。
- 未执行正式 cutover。
- 未保存明文 token。
- 未保存明文 `worker_secret`。
- 未写入真实密码、真实 hash、真实 token 或完整节点链接到文档。

## 验收清单

- `git diff --check`：通过。
- `python3 -X pycache_prefix=/private/tmp/liveline-pycache -m compileall backend/app`：通过。
- `docker compose exec -T backend alembic upgrade head`：通过。
- `docker compose exec -T backend alembic current`：`0008_worker_foundation (head)`。
- `docker compose exec -T frontend npm run build`：通过。
- `docker compose up --build -d`：通过。
- `http://localhost:3000`：HTTP 200。
- `/api/health`：backend / database / redis / worker 全部 ok。
- Redis `temp_credential:*`：0。
- pending / running tasks：0。
- 敏感信息扫描：通过，未发现真实密码、真实 hash、真实 token、SSH Key、完整节点链接或 `SESSION_SECRET` 明文。
