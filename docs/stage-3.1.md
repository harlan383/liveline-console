# Stage 3.1 中转资源管理

Stage 3.1 只实现中转资源管理，用于录入未来可用于中转的普通公网中转服务器、IEPL / IPLC 线路或其他资源。本阶段不做真实中转，不连接远端，不保存任何凭据。

## 已实现范围

- 新增 `transit_resources` 数据表。
- 新增中转资源模型、Schema、API 路由和 Alembic 迁移。
- 新增前端“中转资源”管理面板。
- 支持中转资源列表、详情、新增、编辑、启用和禁用。
- 普通列表展示资源名、类型、状态、服务商、地区、入口 Host 摘要、入口端口、带宽和到期时间。
- `deleted_at` 字段已预留用于后续软删除；本阶段不暴露硬删除功能。

## 字段

`transit_resources` 包含：

- `id`
- `name`
- `resource_type`: `server` / `iepl` / `iplc` / `other`
- `provider`
- `entry_host`
- `entry_port`
- `entry_region`
- `exit_region`
- `bandwidth_mbps`
- `traffic_limit_gb`
- `traffic_used_gb`
- `protocol_hint`: `tcp` / `udp` / `tcp_udp` / `unknown`
- `has_ssh`
- `ssh_host`
- `ssh_port`
- `ssh_username`
- `status`: `active` / `disabled`
- `expires_at`
- `notes`
- `created_at`
- `updated_at`
- `deleted_at`

## API

- `GET /api/transit-resources`
- `POST /api/transit-resources`
- `GET /api/transit-resources/{id}`
- `PATCH /api/transit-resources/{id}`
- `POST /api/transit-resources/{id}/disable`
- `POST /api/transit-resources/{id}/enable`

写操作需要管理员登录和 CSRF。所有接口只读写本地数据库，不需要 SSH Key，不使用 Redis 临时凭据，不创建 RQ 任务。

## 输入校验

- `resource_type` 必须是 `server` / `iepl` / `iplc` / `other`。
- `protocol_hint` 必须是 `tcp` / `udp` / `tcp_udp` / `unknown`。
- `status` 必须是 `active` / `disabled`。
- `entry_port` 和 `ssh_port` 必须在 `1-65535`。
- `bandwidth_mbps`、`traffic_limit_gb`、`traffic_used_gb` 不能为负数。
- `notes` 会拒绝明显的密码、私钥、后台账号、专线密钥等敏感凭据关键词。
- `has_ssh=false` 时，后端会清空 `ssh_host`、`ssh_port`、`ssh_username`。

## 安全边界

Stage 3.1 明确不保存：

- SSH 私钥
- SSH 密码
- IEPL / IPLC 后台账号
- IEPL / IPLC 后台密码
- 专线密钥

前端也不提供 SSH Key、密码、测试连接、配置中转、生成链接等入口。

## 禁止范围

- 不连接香港服务器。
- 不连接 IEPL / IPLC。
- 不连接落地 VPS。
- 不上传或保存 SSH Key。
- 不保存后台账号密码或专线密钥。
- 不新增 Worker 任务。
- 不触发 RQ 任务。
- 不配置转发。
- 不安装 `gost` / `nginx` / `socat` / Xray `dokodemo-door`。
- 不修改 Xray 配置。
- 不修改防火墙。
- 不开放端口。
- 不写 iptables。
- 不调用 3x-ui。
- 不影响当前 active 直连节点。
- 不生成中转客户端链接。
- 不做拓扑预览。
- 不做真实连通性测试。
- 不做流量统计自动采集。
- 不做自动测速。

## Stage 3 后续规划

- Stage 3.2：中转拓扑与配置预览。
- Stage 3.3：香港服务器模拟中转。
- Stage 3.4：真实 IEPL / IPLC 验收。

## Stage 3.1 冻结结论

Stage 3.1 已在真实功能验收后冻结。本阶段只实现中转资源管理，用于保存未来可用于中转的非敏感资源元信息；不连接远端、不保存凭据、不创建 Worker/RQ 任务、不配置真实中转。

冻结依据：

- `transit_resources` 表已创建，Alembic 当前版本为 `0005_transit_defaults`。
- 已实现 `GET /api/transit-resources`、`POST /api/transit-resources`、`GET /api/transit-resources/{id}`、`PATCH /api/transit-resources/{id}`、`POST /api/transit-resources/{id}/disable`、`POST /api/transit-resources/{id}/enable`。
- 前端已新增“中转资源”管理面板。
- 已支持 `server` / `iepl` / `iplc` / `other` 类型资源。
- 已支持列表、详情、新增、编辑、启用和禁用。
- 已确认本阶段不需要 SSH Key，不创建 Worker/RQ 任务，不连接远端。
- 已确认不保存 SSH 私钥、SSH 密码、IEPL 后台账号、IEPL 后台密码或专线密钥。
- 已确认当前 active 直连节点数量仍为 1，未受 Stage 3.1 影响。
- 输入校验已覆盖非法 `resource_type`、非法 `protocol_hint`、端口超范围、负数带宽/流量。
- `notes` 敏感词校验已覆盖 `ssh key`、`SSH KEY`、`ssh_key`、`sshkey`、`private key`、`password=abc`、`token=abc`、`secret=abc`、`后台账号`、`后台密码`。
- 构建与健康检查通过：`python compileall`、`npm run build`、`npm audit`、`docker compose up --build -d`、`/api/health`、Redis 临时凭据检查和 pending/running task 检查。

最终允许范围：

- 中转资源列表。
- 中转资源新增。
- 中转资源详情。
- 中转资源编辑。
- 中转资源启用。
- 中转资源禁用。
- 管理 `server` / `iepl` / `iplc` / `other` 类型资源。
- 保存非敏感的中转资源元信息。
- `notes` 敏感词校验。
- 不保存任何凭据。

最终禁止范围：

- 不连接香港服务器。
- 不连接 IEPL / IPLC。
- 不连接落地 VPS。
- 不上传 SSH Key。
- 不保存 SSH Key。
- 不保存 SSH 密码。
- 不保存 IEPL 后台账号密码。
- 不保存专线密钥。
- 不创建 Worker/RQ 任务。
- 不配置转发。
- 不安装 `gost` / `nginx` / `socat` / Xray `dokodemo-door`。
- 不修改 Xray 配置。
- 不修改防火墙。
- 不开放端口。
- 不写 iptables。
- 不调用 3x-ui。
- 不影响当前 active 直连节点。
- 不生成中转客户端链接。
- 不做拓扑预览。
- 不做真实连通性测试。
- 不做流量统计自动采集。
- 不做自动测速。
