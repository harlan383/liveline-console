# Stage 3.3.41 Node Key Rotation Runbook

## 阶段目标

本阶段新增节点密钥轮换 / 重建节点 / 废弃旧链接操作手册，为未来真正轮换 VLESS Reality 节点做准备。

本阶段只形成 runbook，不执行真实轮换，不重启服务，不修改当前可用节点，也不改变公网运行环境。

## 执行边界

- 不执行 SSH / 远程命令。
- 不连接公网主控 VPS。
- 不连接落地 VPS。
- 不运行 `docker compose`。
- 不查询真实数据库。
- 不触发 `landing_node_create`。
- 不重装 Worker。
- 不安装 Xray。
- 不重启或停止 `liveline-xray`。
- 不创建、删除、轮换或重建节点。
- 不新增监听端口。
- 不修改云安全组 / 云防火墙 / 服务器本机防火墙。
- 不修改数据库。
- 不修改 `node.share_link`。
- 不生成真实节点链接。
- 不执行 cutover。

## 当前正式节点摘要

当前已通过客户端验收的节点只记录为摘要：

```text
node_name = liveline-reality-27939
landing_ip = 64.90.13.19
xray_port = 27939
protocol = vless
transport = tcp
security = reality
flow = xtls-rprx-vision
service_status = active
status = active
client_acceptance = passed
share_link = 已写入但默认脱敏，不展示
```

完整 `vless://` 链接、完整 `node.share_link`、Reality privateKey、完整 Worker setup token、真实密码、`SESSION_SECRET`、数据库密码、完整 UUID、完整 public key、完整 shortId 均不得写入本文档。

## 为什么需要轮换

未来遇到以下任一情况时，应考虑进入节点轮换或废弃流程：

- 完整 `vless://` 链接误贴到聊天、PR、日志或文档。
- 完整 `node.share_link` 外泄到非可信位置。
- Reality privateKey 暴露。
- 客户端设备不再可信，或需要撤销旧客户端访问能力。
- 节点准备从测试用途转为更正式的长期使用。
- 需要废弃旧客户端链接并分发新链接。
- 端口被持续探测、污染，或需要更换监听端口。
- 现有节点配置被怀疑不再可信。

## 轮换等级分级

| 等级 | 名称 | 适用场景 | 影响 |
| --- | --- | --- | --- |
| Level 1 | 只隐藏 / 停止展示链接 | UI 曾展示过链接，但没有外传证据 | 不改节点，仅收紧展示和导出 |
| Level 2 | 重新导出同一 `share_link` 给可信客户端 | 链接仍可信，只是需要重新导入客户端 | 不改节点，不生成新材料 |
| Level 3 | 重建 Reality 材料 | 完整链接疑似外泄，或 UUID / public key / shortId 等连接材料不应继续使用 | 生成新 UUID / key / shortId / `share_link` |
| Level 4 | 更换监听端口并重建节点 | 端口被探测、污染，或需要换端口 | 需要新端口规划、防火墙放行和客户端迁移 |
| Level 5 | 废弃旧节点，创建全新节点 | Reality privateKey 暴露、完整配置外泄或节点被确认不可信 | 新建节点，旧节点后续单独审批停用 / 删除 |

## 推荐默认轮换策略

- 一般完整链接疑似外泄：建议 Level 3。
- Reality privateKey 或完整 Xray 配置外泄：建议 Level 5。
- 只是 UI 展示过但未传播：建议 Level 1 或 Level 2。
- 端口被探测、污染或需要切换端口：建议 Level 4。
- 客户端设备不再可信：至少 Level 3；如涉及私钥或完整配置风险，升级到 Level 5。

## 安全前置检查清单

进入任何真实轮换执行阶段前，必须先确认：

- 当前节点是否正在被客户端使用。
- 是否需要保留旧节点短暂并行，避免客户端中断。
- 是否需要新端口。
- 如果新增或变更监听端口，必须同步确认云服务器安全组已放行对应 TCP 端口。
- 如果新增或变更监听端口，必须同步确认云防火墙已放行对应 TCP 端口。
- 如果新增或变更监听端口，必须同步确认服务器本机防火墙已放行对应 TCP 端口。
- 不在日志、文档、聊天、PR 或 issue 中输出完整 `share_link`。
- 不直接打印或复制完整 Xray 配置。
- 已备份本地 `.env`、`docker-compose.yml` 和必要的运维记录。
- 已用脱敏方式确认 `nodes` 表当前记录，例如只查询 `has_share_link` / `share_link_length` / `masked_share_link`。
- `landing_node_create` 没有 `pending` / `running` 任务。
- 目标 Worker online，且版本满足当时执行阶段要求。
- 当前 `liveline-xray` 服务状态和端口状态已通过只读方式确认。
- 用户明确授权进入对应真实执行阶段。

## 建议的未来真实执行阶段拆分

以下阶段仅为计划，不在本阶段实现：

```text
Stage 3.3.42-formal-node-rotation-execution-approval
Stage 3.3.42-a-new-reality-material-generation
Stage 3.3.42-b-new-node-create-or-replace
Stage 3.3.42-c-client-migration-acceptance
Stage 3.3.42-d-old-node-retirement-approval
Stage 3.3.42-e-old-node-disable-or-delete
```

建议拆分原因：

- 先审批目标、风险、端口和回滚窗口。
- 再生成新 Reality 材料或创建新节点。
- 再由客户端验收新链接。
- 新节点确认可用后，再单独审批旧节点废弃。
- 旧节点停止、删除、端口释放必须单独审批，不能和新节点创建混在一个阶段。

## 回滚策略

- 如果新节点创建失败，不删除旧节点。
- 如果新节点客户端不可用，继续保留旧节点。
- 如果新节点服务启动失败，只清理本次新增内容，不删除未知已有文件。
- 如果新节点可用，再进入旧节点废弃审批。
- 所有删除、停止、端口释放、旧链接废弃都必须单独审批。
- 不得在轮换失败时自动修改 `node.share_link` 指向未知或未验收链接。
- 不得删除非 LiveLine 管理的 Xray、systemd 或业务文件。

## 数据库与链接安全策略

- 默认查询只显示 `has_share_link`、`share_link_length`、`masked_share_link`。
- 不直接 `SELECT share_link`。
- 不把完整链接写入 README、docs、PR、issue、聊天、终端日志或任务日志。
- 导出完整链接必须走二次确认接口。
- 导出后只用于可信客户端导入。
- QR code 等同完整链接，必须按完整链接处理。
- 排障输出必须排除或打码 `share_link`、`secure_share_link`、`client_link` 等字段。
- Reality privateKey 永远不得写入日志、文档、PR 或聊天记录。

## 当前阶段结论

- 本阶段只形成节点密钥轮换 runbook。
- 不轮换当前 `liveline-reality-27939`。
- 不重启或停止 `liveline-xray`。
- 不修改 `node.share_link`。
- 不生成真实节点链接。
- 不新增监听端口。
- 不执行 cutover。
- 后续如果需要真实轮换，应先进入 `Stage 3.3.42-formal-node-rotation-execution-approval`。

## 后续建议

- `Stage 3.3.42-formal-node-rotation-execution-approval`
- `Stage 3.3.43-transit-integration-planning`

## 验收清单

- `git diff --check` 通过。
- `python3 -m compileall backend/app` 通过。
- 敏感信息扫描不发现完整 `vless://`、Reality privateKey、完整 `share_link`、完整 Worker setup token、真实密码、`SESSION_SECRET`、数据库密码、完整 UUID、完整 public key 或完整 shortId。
