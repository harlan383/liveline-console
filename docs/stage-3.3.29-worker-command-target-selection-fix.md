# Stage 3.3.29 Worker Command Target Selection Fix

## 本阶段目标

修复 Worker 检查命令在同一 `server_id` 下存在多个 Worker 记录时，可能错误下发到旧版 Worker 的问题。

本阶段只修复本地后端目标选择逻辑、API 返回字段、前端展示和文档，不执行 SSH / 远程命令，不创建节点，不创建中转链路，不新增监听端口，不修改 `node.share_link`，不执行正式 cutover。

## 真实问题

Stage 3.3.28 增加了 Worker command channel。公网主控和落地 VPS 升级后，同一台落地服务器记录下可能同时存在：

- 新版 Worker：`0.1.1-stage-3.3.28`，支持 command polling。
- 旧版 Worker：`0.1.0-stage-3.3.24`，不支持 command polling。
- 更早未绑定 Worker：`server_id` 为空，不应作为命令目标。

之前管理员创建命令接口直接信任前端传入的 `worker_id`。如果该 ID 是旧 Worker，命令会一直停留在 `pending`。

## 目标选择规则

新增 Worker 目标选择 helper：

`resolve_command_target_worker(db, server_type, server_id, role=None, requested_worker_id=None)`

选择规则：

1. 只选择 `status = online` 且运行时状态仍在线的 Worker。
2. 必须匹配同一个 `server_id`。
3. `role` 必须匹配：
   - 落地服务器：`landing`
   - 中转服务器：`transit`
4. 必须支持 command channel。
5. 如果多个 Worker 都可执行命令，选择 `last_heartbeat_at` 最新的；若相同，选择 `registered_at` 最新的。
6. 如果解析出的目标 Worker 和请求中的 Worker 不一致，后端自动使用最新可执行命令的 Worker。

## Command-capable 判断

最低支持版本：

`0.1.1-stage-3.3.28`

版本解析不会使用简单字符串比较，而是拆分为：

- 主版本：`major.minor.patch`
- 阶段版本：`stage-x.y.z`

以下情况都视为不支持 command channel：

- `worker_version` 为空。
- `worker_version` 为 `unknown` 或不可解析。
- `worker_version` 小于 `0.1.1-stage-3.3.28`。
- 典型旧版本：`0.1.0-stage-3.3.24`。

## 错误码

- `WORKER_NOT_BOUND`：Worker 没有绑定服务器记录，或服务器没有绑定 Worker。
- `WORKER_OFFLINE`：该服务器没有在线 Worker。
- `WORKER_COMMAND_UNSUPPORTED`：当前在线 Worker 不支持命令通道，需要重新安装或升级 `liveline-worker`。

没有 command-capable Worker 时，后端不会创建新的 `pending` 命令。

## API 行为

管理员创建命令接口仍为：

`POST /api/workers/{worker_id}/commands`

修复后：

- 前端可以继续传 `worker_id`。
- 后端不会盲信该 `worker_id`。
- 如果请求体带 `server_id` / `server_type`，后端按服务器重新解析最佳 Worker。
- 如果请求体没有服务器信息，后端从请求 Worker 反查 `server_id` 和 `role`。
- 命令最终写入 command-capable 的目标 Worker。
- 响应返回 `target_worker_id`、`target_worker_version`、`target_worker_changed` 和 `minimum_supported_worker_version`。

## 前端展示

落地服务器和中转服务器的 `Worker 检查` 按钮会传入当前服务器记录的 `server_id` 和角色：

- 落地服务器：`landing`
- 中转服务器：`transit`

创建成功后，页面显示：

- `command_id`
- `target_worker_id`
- `target_worker_version`
- 命令状态
- 结果摘要或错误信息

页面刷新后会读取当前 Worker 的最近命令，避免已成功命令摘要刷新后消失。

## 旧 pending 命令处理

本阶段采用安全方案 A：

- 不删除旧 pending 命令。
- 不批量修改历史命令状态。
- 只确保新命令不会继续发给不支持 command polling 的旧 Worker。

## 修改文件

- `backend/app/services/worker_targeting.py`
- `backend/app/services/worker_commands.py`
- `backend/app/schemas/worker_commands.py`
- `backend/app/api/routes/workers.py`
- `frontend/lib/api.ts`
- `frontend/components/ServerManagementPanel.tsx`
- `frontend/components/TransitRoutesPanel.tsx`
- `README.md`
- `docs/stage-3.3.29-worker-command-target-selection-fix.md`

## 验收结果

- `git diff --check`：通过。
- `python3 -m compileall backend/app`：本机 macOS Python cache 权限阻止普通命令写入系统缓存；使用 `python3 -X pycache_prefix=/private/tmp/liveline-pycache -m compileall backend/app` 验证通过。
- `docker compose exec -T frontend npm run build`：通过。
- `docker compose up --build -d`：通过。
- `docker compose exec -T backend alembic current`：通过，无新增 migration。
- `/api/health`：backend / database / redis / worker 全部 ok。
- Redis `temp_credential:*`：0。
- pending / running tasks：0。
- 本地模拟同一 `server_id` 下新旧 Worker：新命令下发到新版 Worker。
- 仅旧 Worker 在线时：返回 `WORKER_COMMAND_UNSUPPORTED`，不创建 pending 命令。
- 无在线 Worker 时：返回 `WORKER_OFFLINE`。
- Worker 无 `server_id` 时：返回 `WORKER_NOT_BOUND`。
- 敏感信息扫描：未发现真实 SSH Key、真实密码、token、SESSION_SECRET 真实值或完整节点链接。

## 安全边界

- 是否新增 migration：否。
- 是否执行 SSH / 远程命令：否。
- 是否创建节点：否。
- 是否创建中转链路：否。
- 是否新增监听端口：否。
- 是否修改 `node.share_link`：否。
- 是否执行 cutover：否。
- 是否删除旧 Worker 记录：否。
- 是否明文写入 token / worker_secret：否。
