# Stage 3.4.0 UI customer-first line builder

## Summary

Stage 3.4.0 reorganizes the frontend around customer-facing workflows instead of the previous engineering-first panels.

The new main navigation is:

- 总览
- 线路搭建
- 客户线路
- 服务器资源
- 任务记录
- 设置
- 高级调试

The ordinary UI now emphasizes customers, use cases, line type, server resources, client configuration status, and task summaries. Existing technical operations remain available under 高级调试.

## Customer-First Panels

### 线路搭建

The new Line Builder page reads existing local API data and shows:

- 新建直连节点
- 新建中转线路（自建中转）
- 新建中转线路（商家中转）
- 添加服务器资源

For Stage 3.4.0 these are readonly planning entries. Real create actions are disabled and marked for a later stage.

The wizard captures:

- Customer assignment
- Usage purpose
- Line type
- Readonly path preview

It also keeps the port reminder:

新增或变更客户连接端口后，请务必同步检查云服务器安全组、云防火墙、服务器防火墙是否放行。

### 客户线路

The Customer Lines page groups existing direct nodes and transit routes by frontend-derived customer labels. This stage does not add a customer database.

Customer, platform, and usage classification are derived from current names and notes:

- 客户A / 客户B / 自己使用 / 未分配
- Facebook / TikTok / YouTube / 未设置
- 主线 / 备用 / 测试 / 日常 / 未设置

The page keeps detail, copy, and QR affordances only for links already available to the frontend. QR generation remains browser-local.

### 服务器资源

The Server Resources page shows:

- 落地服务器
- 中转服务器（自建）
- 商家中转入口

It uses business-facing terms such as 服务器助手 and 客户连接入口 instead of exposing low-level implementation details in the main UI.

### 任务记录

The task page now presents business columns:

- 时间
- 任务名称
- 关联对象
- 当前状态
- 结果说明
- 操作

Task IDs, raw task type, result JSON, and logs are available only inside 查看技术详情.

### 高级调试

The previous technical workbench remains available under 高级调试. This preserves access to low-level server, route, worker, command, and diagnostics views without placing them in the ordinary user path.

## Safety Boundary

This stage is frontend information architecture only.

No backend API was changed.

No database schema or data was changed.

No Worker code or binary was changed.

No remote command, SSH, deployment, node creation, transit route creation, deletion, cutover, firewall change, or listener change was performed.

No `nodes.share_link` or `transit_routes.share_link` was modified.

No full client link, UUID, private key, public key, short ID, token, or secret is documented here.
