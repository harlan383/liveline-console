# Stage 3.2 中转拓扑与配置预览

Stage 3.2 只实现前端本地“中转拓扑与配置预览”。用户可以选择一个已启用的中转资源和一个 active 节点，输入预期中转入口端口，选择未来可能使用的转发方式，然后在浏览器中查看拓扑与配置预览。

本阶段不保存 route，不连接任何远端，不配置中转，不生成真实可用链接。

## 已实现范围

- 新增前端“中转拓扑预览”面板。
- 复用 `GET /api/transit-resources` 获取 active 中转资源。
- 复用 `GET /api/nodes` 获取 active 节点。
- 支持选择中转资源。
- 支持选择 active 节点。
- 支持输入预期中转入口端口。
- 支持选择预览转发方式：
  - `gost`
  - `nginx_stream`
  - `socat`
  - `xray_dokodemo`
  - `manual`
  - `unknown`
- 在前端本地展示拓扑：
  `client -> transit resource -> landing VPS / node -> platform`
- 在前端本地生成配置预览文本。
- 预览文本明确标记 `PREVIEW ONLY`、`NOT USABLE`、未连接远端、未写入配置、未完成真实中转配置。

## 配置预览

`server` 类型资源预览包含：

- 资源类型：公网中转服务器。
- 未来链路：`client -> transit server -> landing VPS/node -> platform`。
- 预期监听端口。
- 目标地址：landing VPS IP。
- 目标端口：节点端口。
- 转发方式预览。
- 明确说明本阶段不安装工具、不写配置、不生成可用链接。

`iepl` / `iplc` 类型资源预览包含：

- 资源类型：IEPL / IPLC 线路。
- 入口 host / port。
- 出口地区。
- 落地节点、landing VPS IP、节点端口。
- 供应商侧可能负责入口到出口映射。
- 本系统后续阶段才考虑落地侧配置。
- 明确说明本阶段不验证线路、不连接供应商、不连接落地 VPS。

`other` 类型资源只展示通用拓扑和待确认的配置责任边界。

## 数据与安全边界

- 不新增 `transit_routes` 表。
- 不新增 `forwarding_rules` 表。
- 不新增数据库字段。
- 不新增 Alembic。
- 不新增后端 API。
- 不新增 Worker/RQ 任务。
- 不触发任何任务。
- 不创建 `task_logs`。
- 不显示完整 `share_link`。
- 不显示 Reality privateKey。
- 不显示 SSH Key。
- 不显示 SSH 密码。
- 不把 `notes` 内容放入配置预览。

## 禁止范围

- 不连接香港服务器。
- 不连接 IEPL / IPLC。
- 不连接落地 VPS。
- 不上传 SSH Key。
- 不保存 SSH Key。
- 不配置转发。
- 不安装 `gost` / `nginx` / `socat` / Xray `dokodemo-door`。
- 不修改 Xray 配置。
- 不修改防火墙。
- 不开放端口。
- 不写 iptables。
- 不调用 3x-ui。
- 不影响当前 active 节点。
- 不修改 `nodes` 表。
- 不修改 `vps_servers` 表。
- 不生成真实可用中转链接。
- 不生成二维码。
- 不做真实连通性测试。
- 不做流量统计自动采集。
- 不做自动测速。

## Stage 3 后续规划

- Stage 3.3：香港服务器模拟中转。
- Stage 3.4：真实 IEPL / IPLC 验收。

## Stage 3.2 冻结结论

Stage 3.2 已在真实功能验收后冻结。本阶段是纯前端本地预览，只复用现有 `GET` 接口，不新增后端 API、不新增数据库表、不新增 Alembic、不新增 Worker/RQ 任务、不连接远端、不配置中转、不生成真实可用中转链接。

冻结依据：

- Docker Compose 5 个容器运行正常。
- `/api/health` 返回 backend、database、redis、worker 全部 ok。
- Alembic 仍为 `0005_transit_defaults`。
- `npm audit` 返回 `found 0 vulnerabilities`。
- Redis `temp_credential:*` 为 0。
- pending/running tasks 为 0。
- 当前 active 节点数量仍为 1。
- active `transit_resources` 为 4 条。
- 未新增 `transit-routes` API。
- 未新增 `transit_routes` 表。
- 未新增 `forwarding_rules` 表。
- 未新增 Worker/RQ task 类型。
- AppShell 中存在“中转拓扑预览”面板和“拓扑预览”导航项。
- 页面没有 SSH Key 输入框、测试连接按钮、执行配置按钮、安装转发工具按钮或生成正式链接按钮。
- `server`、`iepl`、`iplc` 预览均通过验收。
- `gost`、`nginx_stream`、`socat`、`xray_dokodemo`、`manual`、`unknown` 均只作为本地预览，不执行远端命令。
- 预览明确显示 `PREVIEW ONLY`、`NOT USABLE`、未连接远端、未写入配置、未完成真实中转配置。
- 未生成正式可复制中转 `vless://` 链接，未生成二维码。
- 拓扑预览不显示完整 `share_link`、Reality privateKey、SSH Key、SSH 密码，`notes` 内容不进入配置预览。

最终允许范围：

- 前端中转拓扑预览。
- 选择 active `transit_resource`。
- 选择 active node。
- 输入预期中转入口端口。
- 选择 `forwarding_method`。
- 本地生成拓扑文本。
- 本地生成配置预览文本。
- 显示 `PREVIEW ONLY` / `NOT USABLE`。
- 区分 `server` / `iepl` / `iplc` 预览说明。
- 不保存 route。
- 不连接远端。

最终禁止范围：

- 不新增 `transit_routes` 表。
- 不新增 `forwarding_rules` 表。
- 不新增数据库字段。
- 不新增 Alembic。
- 不新增后端 API。
- 不新增 Worker/RQ 任务。
- 不触发任何任务。
- 不连接香港服务器。
- 不连接 IEPL / IPLC。
- 不连接落地 VPS。
- 不上传 SSH Key。
- 不保存 SSH Key。
- 不配置转发。
- 不安装 `gost` / `nginx` / `socat` / Xray `dokodemo-door`。
- 不修改 Xray 配置。
- 不修改防火墙。
- 不开放端口。
- 不写 iptables。
- 不调用 3x-ui。
- 不影响当前 active 节点。
- 不修改 `nodes` 表。
- 不修改 `vps_servers` 表。
- 不生成真实可用中转链接。
- 不生成二维码。
- 不做真实连通性测试。
- 不做流量统计自动采集。
- 不做自动测速。
