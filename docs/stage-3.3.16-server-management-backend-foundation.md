# Stage 3.3.16 Server Management Backend Foundation

## 当前阶段结论

本阶段补齐“服务器管理”表格页所需的最小后端基础能力。Stage 3.3.15 曾停止在后端能力检查阶段，原因是现有模型和 API 不能完整支撑服务器名称、SSH 握手状态、失败原因、服务器列表、编辑、删除和下级节点聚合展示。

本阶段不是正式 cutover，不修改 `node.share_link`，不新增真实监听端口，不创建真实节点，不创建中转链路，不自动清理远程服务器配置。

## 新增 vps_servers 字段

本阶段新增一个 Alembic 迁移：

`backend/alembic/versions/0007_add_vps_server_management_fields.py`

新增字段：

| 字段 | 用途 |
| --- | --- |
| `name` | 服务器管理页显示的服务器名称 |
| `notes` | 本地备注，不允许写入密码、私钥、token 或完整节点链接 |
| `last_ssh_check_at` | 最近一次 SSH 握手检测时间 |
| `last_ssh_status` | 服务器管理页专用 SSH 状态，取值为 `unchecked` / `online` / `offline` |
| `last_ssh_error` | 最近一次 SSH 握手失败原因摘要 |

`last_ssh_status` 只表示最近一次 SSH 通讯握手结果，不代表节点可用，不代表 Xray 正常，也不代表当前线路可用。

## 新增或完善的 API

### GET /api/vps

返回服务器列表和下级节点摘要，供服务器管理表格使用。

服务器字段包括：

* `id`
* `name`
* `ip`
* `ssh_port`
* `ssh_user`
* `notes`
* `status`
* `last_ssh_status`
* `last_ssh_check_at`
* `last_ssh_error`
* `created_at`
* `updated_at`
* `nodes`

下级节点摘要包括：

* `id`
* `name`
* `address` / `ip`
* `port`
* `protocol`
* `status`
* `share_link_present`
* `created_at`

本阶段不返回完整 `share_link`，只返回是否存在。

### POST /api/vps

添加服务器记录并创建 `check_vps_ssh` 握手检测任务。

请求字段：

* `name`
* `ip`
* `ssh_port`
* `ssh_user`
* `notes`
* `private_key_text` 或 `private_key_file`
* `private_key_passphrase` / `ssh_key_passphrase`

处理规则：

* 请求参数格式错误时不创建记录。
* 私钥不会明文保存。
* 私钥通过现有 Redis 临时凭据机制传给 Worker。
* API 返回 `task_id` 和 `vps_id`。
* Worker 握手成功后写入 `last_ssh_status=online`、`last_ssh_check_at` 和清空 `last_ssh_error`。
* Worker 握手失败后保留服务器记录，写入 `last_ssh_status=offline`、`last_ssh_check_at` 和失败原因摘要。

### POST /api/vps/{vps_id}/recheck

重新检测服务器 SSH 连通性。

处理规则：

* 默认使用服务器记录里的 IP、SSH 端口和 SSH 用户名。
* 可选覆盖 `ssh_port` / `ssh_user`，覆盖后会按新值检测。
* 私钥仍通过 Redis 临时凭据机制传递，不保存明文。
* 成功更新为 `online`，失败更新为 `offline`。

### PATCH /api/vps/{vps_id}

编辑服务器基础信息。

允许编辑：

* `name`
* `ip`
* `ssh_port`
* `ssh_user`
* `notes`

不允许直接编辑：

* `last_ssh_status`
* `last_ssh_check_at`
* `last_ssh_error`

如果修改了 IP、SSH 端口或 SSH 用户名，系统会把 `last_ssh_status` 重置为 `unchecked`，并提示需要重新检测。

### DELETE /api/vps/{vps_id}

删除服务器系统记录。

当前项目没有 `vps_servers.deleted_at` 字段，因此本阶段采用最小兼容策略：

* 将服务器 `status` 标记为 `deleted`，使其不再出现在 `GET /api/vps`。
* 将该服务器下未删除的节点标记为 `deleted` 并写入 `nodes.deleted_at`。
* 只删除/隐藏本系统记录。
* 不 SSH 登录远程服务器。
* 不自动清理远程 Xray、节点配置或系统服务。

返回结果会说明：

* 删除的服务器 id
* 受影响节点数量
* `system_record_only=true`
* `remote_cleanup_performed=false`

## SSH 握手任务

新增任务类型：

`check_vps_ssh`

任务边界：

* 可以 SSH 连接服务器。
* 可以执行固定只读命令读取基础系统信息。
* 可以判断 SSH 是否成功。
* 可以记录失败原因摘要。
* 不安装 Xray。
* 不创建节点。
* 不创建中转链路。
* 不修改 `node.share_link`。
* 不新增监听端口。
* 不执行正式 cutover。

本阶段复用现有 Redis 临时凭据机制。Worker 读取临时凭据后会通过 `pop_temp_credential` 删除 Redis 中的临时凭据。

## SSH 私钥安全规则

* 不保存明文 SSH 私钥。
* 不把私钥写入数据库普通字段。
* 不把私钥写入日志。
* 不把私钥写入任务结果。
* 不把私钥写入 README 或阶段文档。
* 不通过 API 响应返回私钥。
* 不在浏览器可见状态展示私钥。

## 前端范围

本阶段不做完整服务器管理表格 UI。前端只补充 `frontend/lib/api.ts` 的 VPS 管理数据类型，供下一阶段 UI 对接。

完整服务器管理表格页留到 Stage 3.3.17。

## 安全边界

* 是否修改 `node.share_link`：否。
* 是否新增监听端口：否。
* 是否创建真实节点：否。
* 是否创建中转链路：否。
* 是否执行正式 cutover：否。
* 是否保存明文 SSH 私钥：否。
* 是否复用 Redis 临时凭据机制：是。
* 是否执行远程 SSH：本阶段代码支持由 API 触发 SSH 握手任务；本阶段验收不直接连接真实服务器。

## 验收清单

* `git diff --check` 通过。
* Alembic 迁移可升级到 head。
* 后端 Python 编译通过。
* 前端构建通过。
* Docker Compose 可启动。
* `/api/health` 正常。
* Redis `temp_credential:*` 为 0。
* pending / running tasks 为 0。
* 敏感信息扫描未发现真实 SSH 私钥、真实密码、Passphrase、token、完整节点链接、`SESSION_SECRET` 真实值或真实 hash。
