# Stage 3.3.28 Worker Command Channel Foundation

## 本阶段目标

本阶段实现主控向已接入的 `liveline-worker` 下发只读 / no-op 命令的基础通道，为后续通过 Worker 创建落地节点、创建中转链路做准备。

本阶段只做命令队列、Worker 拉取命令、Worker 回报结果、Go Worker polling 和最小 UI 检查入口。本阶段不执行真实远程写操作。

## 为什么需要 Worker 命令通道

Stage 3.3.27 已完成服务器记录与 Worker 绑定，但 Worker 只支持注册、心跳和状态上报。后续如果要通过 Worker 做节点创建、中转链路创建或远程诊断，需要先有一个可审计、可租约、可上报结果的基础命令通道。

Stage 3.3.28 只建立这个基础通道，并且严格限制为只读 / no-op 命令。

## 新增数据库结构

新增 Alembic migration：

- `backend/alembic/versions/0009_worker_command_channel.py`

新增表：

- `worker_commands`

字段：

- `id`
- `worker_id`
- `server_type`
- `server_id`
- `command_type`
- `payload_json`
- `status`
- `lease_until`
- `claimed_at`
- `completed_at`
- `result_json`
- `error_message`
- `attempts`
- `created_at`
- `updated_at`

安全边界：

- 不保存 token 明文。
- 不保存 `worker_secret` 明文。
- 不保存 SSH 私钥。
- 不保存 SSH passphrase。
- 不保存完整节点链接。
- 不保存远程敏感配置。
- payload / result 经过基础脱敏和截断。

## 新增命令类型

第一版只允许：

- `ping`
- `collect_status`
- `service_status`

明确禁止：

- `create_node`
- `create_route`
- `restart_service`
- `install`
- `delete`
- `cleanup`
- 任何修改远程状态的命令。

## 后端 API

Worker 自用 API：

- `POST /api/workers/commands/next`
- `POST /api/workers/commands/{command_id}/result`
- `POST /api/workers/commands/{command_id}/fail`

这些接口使用现有 Worker 鉴权：

- `X-Worker-Id`
- `X-Worker-Secret`

管理员 API：

- `POST /api/workers/{worker_id}/commands`
- `GET /api/workers/{worker_id}/commands`

管理员创建命令仍受登录 session 和 CSRF 保护。

## Worker Polling 设计

Go Worker 保留原有 heartbeat loop，同时新增 command polling loop。

行为：

- 每约 20 秒调用 `/api/workers/commands/next`。
- 没有命令时继续等待。
- 有命令时按 `command_type` 执行。
- 成功后上报 result。
- 失败后上报 fail。

只读命令行为：

- `ping`：返回 `pong`、worker version、hostname、role、interface 和时间戳。
- `collect_status`：返回 hostname、OS、kernel、uptime、CPU、memory、disk、interface、worker version、service summary。
- `service_status`：只读检查服务状态。landing role 检查 liveline-worker / xray；transit role 检查 liveline-worker / socat / gost。

只读命令允许使用：

- `systemctl is-active`
- `command -v`
- 本地只读系统文件读取，如 `/etc/os-release`、`/proc/uptime`、`/proc/meminfo`。

禁止：

- `systemctl restart`
- `systemctl stop`
- `systemctl enable`
- 写文件
- 改配置
- 安装软件
- 开端口
- 修改防火墙
- 修改 Xray / socat / gost

## UI 入口

落地服务器页面：

- Worker 在线的落地服务器显示 `Worker 检查`。
- 点击后创建 `collect_status` 命令。
- 页面显示最近命令状态、结果摘要或错误原因。
- 不执行 SSH。
- 不创建节点。

中转服务器页面：

- Worker 在线的中转服务器显示 `Worker 检查`。
- 点击后创建 `collect_status` 命令。
- 页面显示最近命令状态、结果摘要或错误原因。
- 不执行 SSH。
- 不创建中转链路。

## 修改文件

- `backend/app/models/worker_command.py`
- `backend/app/models/__init__.py`
- `backend/app/db/base.py`
- `backend/alembic/versions/0009_worker_command_channel.py`
- `backend/app/schemas/worker_commands.py`
- `backend/app/services/worker_commands.py`
- `backend/app/api/routes/workers.py`
- `worker/cmd/liveline-worker/main.go`
- `backend/worker-binaries/liveline-worker-linux-amd64`
- `frontend/lib/api.ts`
- `frontend/components/ServerManagementPanel.tsx`
- `frontend/components/TransitRoutesPanel.tsx`
- `frontend/app/globals.css`
- `README.md`
- `docs/stage-3.3.28-worker-command-channel-foundation.md`

## 验收结果

- `python3 -X pycache_prefix=/private/tmp/liveline-pycache -m compileall backend/app`：通过。
- `docker compose exec -T backend alembic upgrade head`：通过。
- `docker compose exec -T backend alembic current`：`0009_worker_command_channel (head)`。
- `/usr/local/go/bin/go version`：`go1.26.4 darwin/arm64`。
- `GOCACHE=/private/tmp/liveline-go-cache /usr/local/go/bin/go test ./...`：通过。
- `GOCACHE=/private/tmp/liveline-go-cache /usr/local/go/bin/go build -o /tmp/liveline-worker ./cmd/liveline-worker`：通过。
- Linux amd64 Worker binary 已重新生成：`backend/worker-binaries/liveline-worker-linux-amd64`。
- `docker compose exec -T frontend npm run build`：通过。
- `docker compose up --build -d`：通过。
- `http://localhost:3000`：HTTP 200。
- `/api/health`：backend / database / redis / worker 全部 ok。
- Redis `temp_credential:*`：0。
- pending / running tasks：0。
- Worker 命令轮询接口无认证返回 401：通过。
- 临时本地 Worker 测试中，所属 Worker 可拉取 `ping` 命令：通过。
- 非所属 Worker 不能提交命令结果：通过。
- 所属 Worker 可提交命令结果：通过。
- 写操作命令不在白名单：通过。
- 临时测试 Worker 和命令记录已清理：通过。
- 敏感信息扫描：通过，未发现真实 SSH Key、真实密码、token、`SESSION_SECRET` 真实值、完整节点链接或 `node.share_link` 明文样例。

## 安全边界

- 是否新增 migration：是，新增 `0009_worker_command_channel.py`。
- 是否执行 SSH / 远程命令：否。
- 是否连接真实 VPS：否。
- 是否创建节点：否。
- 是否创建中转链路：否。
- 是否新增监听端口：否。
- 是否修改 `node.share_link`：否。
- 是否修改 Xray：否。
- 是否修改 socat / gost：否。
- 是否清理远程服务器：否。
- 是否安装或升级真实 VPS 上的 Worker：否。
- 是否执行正式 cutover：否。

## 后续建议

- 后续如需让真实 VPS 使用新的 command polling，需要用户手工重新执行安装命令，或单独进入 Worker upgrade 阶段。
- 后续如需新增会修改远程状态的命令，必须单独审批，并明确命令白名单、回滚策略和敏感信息边界。
- 后续创建节点、创建中转链路、远程清理、修改 Xray / socat / gost、cutover 均必须另开阶段。
