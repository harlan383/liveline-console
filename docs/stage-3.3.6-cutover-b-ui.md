# Stage 3.3.6 Cutover B UI

Stage 3.3.6 只实现 Cutover 方案 B 的前端展示增强。本阶段不是正式 cutover，不修改正式节点链接，不修改中转线路数据，不连接服务器，不触发任务。

## 本阶段目标

在“单条转发 -> 中转线路管理”中，将已通过客户端连通性验收的 `socat` 18443 链路从“测试链路”提升为“候选正式链路”展示，并提供清晰的复制入口。

## 当前链路关系

- `gost` 8443
  - route：`hk-gost-test-8443`
  - 状态：保留
  - 定位：当前正式/回退链路
- `socat` 18443
  - route：`hk-socat-test-18443`
  - 状态：active
  - 定位：候选正式链路
  - 已完成 Shadowrocket 客户端连通性验证

当前仍未正式 cutover。`gost` 8443 未停用，`socat` 未接管 8443。

## 前端实现范围

- 页面顶部显示 Cutover 状态提示。
- 明确显示：
  - 当前尚未正式 cutover。
  - `gost` 8443 仍保留为当前正式/回退链路。
  - `socat` 18443 已通过测试，本阶段只是候选正式链接展示。
  - 本页面不会修改 `node.share_link`。
  - 本页面不会停用 `gost`，也不会让 `socat` 接管 8443。
- `socat` 18443 route 卡片显示“候选正式链路 / 尚未 cutover”。
- `gost` 8443 route 卡片显示“当前正式/回退链路 / 保留”。
- `socat` 18443 route 卡片新增“socat 18443 候选正式链接”区域。
- 候选链接由当前 active Reality node 的 `share_link` 前端派生。
- 复制候选链接前显示确认提示。

## 候选链接生成规则

候选链接只在浏览器前端生成：

- 从当前 active node 的 `share_link` 派生。
- 仅将 server 改为 `163.223.216.108`。
- 仅将 port 改为 `18443`。
- UUID、flow、Reality、SNI、publicKey、shortId、fingerprint、spiderX 等参数保持不变。
- 不写数据库。
- 不替换 `node.share_link`。
- 不输出完整链接到文档、日志或任务结果。

如果页面缺少 `node.share_link`，则只显示提示：当前页面缺少 `node.share_link`，暂不能生成候选正式链接。

## 禁止范围

- 不修改 `.env`。
- 不修改私钥。
- 不修改服务器密码。
- 不修改真实数据库。
- 不修改真实日志。
- 不修改 `node.share_link`。
- 不修改 `transit_routes`。
- 不修改 `transit_routes.active` 或类似语义。
- 不删除、停用、重启、替换 `gost` 8443。
- 不让 `socat` 接管 8443。
- 不新增后端 API。
- 不新增 Worker / RQ 任务。
- 不触发后端任务。
- 不连接 VPS 或中转服务器。
- 不执行远程 SSH 命令。
- 不修改远程服务器配置。
- 不修改 Xray、防火墙、iptables、nft 或云安全组。
- 不新增数据库迁移。
- 不新增 Alembic 文件。
- 不新增表或字段。
- 不新增监听端口。
- 不生成二维码、订阅链接、流量统计或测速。

## 是否修改 node.share_link

否。本阶段只展示和复制前端派生的候选正式链接，不写入 `nodes.share_link`。

## 是否新增数据库迁移

否。本阶段不新增数据库迁移，不新增 Alembic 文件，不新增表，不新增字段。

## 是否新增监听端口

否。本阶段继续复用已验证的 `socat` 18443。`gost` 8443 仍保留，不新增或变更任何监听端口。

## 回滚方式

本阶段不写库、不触发任务、不连接服务器，因此回滚只需要回退前端展示代码。用户侧如果候选链接不可用，可继续使用原直连链接或 `gost` 8443 回退链路。

## Workbuddy 本地验证步骤

1. 确认当前分支为 `stage-3.3.6-cutover-b-ui`。
2. 执行 `npm run build`。
3. 执行 `docker compose up --build -d`。
4. 检查 `/api/health` 返回 backend / database / redis / worker 全部 ok。
5. 检查 Redis `temp_credential:*` 为 0。
6. 检查 pending / running tasks 为 0。
7. 打开前端“单条转发 -> 中转线路管理”。
8. 确认页面明确显示“尚未正式 cutover”。
9. 确认 `gost` 8443 显示为当前正式/回退链路。
10. 确认 `socat` 18443 显示为候选正式链路。
11. 确认 `socat` 18443 候选链接可复制。
12. 确认复制前有确认提示。
13. 确认复制出的链接只改变 server 和 port，不改变 Reality 参数。
14. 确认没有新增任务。
15. 确认没有修改 `node.share_link`。
16. 确认没有新增数据库迁移和监听端口。

## Runtime acceptance result

Stage 3.3.6 已完成前端运行验收。本次归档只记录本地运行结果，不代表正式 cutover，也不代表完整 Docker 部署验收通过。

验收环境：

- 当前分支：`main`
- `git status`：clean
- Node：`v22.22.2`
- npm：`10.9.7`
- 架构：`arm64`
- Next：`15.5.18`
- `@next/swc-darwin-arm64`：已存在，版本 `15.5.18`

验收结果：

- `npm install`：通过，`0 vulnerabilities`
- `npm run build`：通过
- Next build：`Compiled successfully`
- Linting and checking validity of types：通过
- 前端页面：`http://localhost:3000` 返回 `200`
- `@next/swc-darwin-arm64` 缺失问题已通过重新安装依赖解决
- `next dev` 前端页面已能正常打开

Docker compose 验收：

- Docker compose 未通过
- 原因：本地 Docker Buildx 沙箱权限被拒
- 该问题属于当前本地环境限制，不是 Stage 3.3.6 代码验收失败
- 因此 Stage 3.3.6 只能标记为“前端运行验收通过”
- Stage 3.3.6 不能标记为“完整 Docker 部署验收通过”

运行验收后的安全边界确认：

- 未修改 `node.share_link`
- 未新增 Alembic 迁移
- 未新增后端 API
- 未新增 Worker / RQ task
- 未新增监听端口
- 未执行远程命令
- 未触发后端任务
- `gost` 8443 仍保留
- `socat` 18443 仍只是候选正式链路展示
- 当前尚未正式 cutover

## 下一阶段建议

如果 Stage 3.3.6 验收通过，下一阶段仍不应直接进入高风险 cutover。建议先单独评审是否需要：

- Stage 3.3.7：候选链接客户端复验与只读状态快照。
- 或单独计划 Cutover 方案 C / 正式写入 `node.share_link` 的风险评审。

任何正式 cutover 前，必须再次确认是否修改 `node.share_link`、是否停用 `gost` 8443、是否需要远端操作和回滚方案。
