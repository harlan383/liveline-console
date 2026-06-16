# Stage 3.3.36 Formal Landing Node Create Execution Guard

## 当前阶段目标

本阶段为正式创建落地节点前的 execution guard 阶段，不是真实执行阶段。本阶段只补充最后执行保护、dry-run 提示和审批记录，不安装 Xray，不创建节点，不新增监听端口，不修改防火墙，不修改 `node.share_link`，不生成真实节点链接，不执行 cutover。

## 已确认审批条件

| 项目 | 当前确认 |
| --- | --- |
| 候选端口 | `27939/TCP` |
| 云安全组 | 已放行 `27939/TCP` |
| 云防火墙 | 已放行 `27939/TCP` |
| 服务器本机防火墙 | 已放行 `27939/TCP` |
| 允许安装 Xray-core | 是，后续真实执行阶段才允许 |
| 允许创建 VLESS Reality 落地节点 | 是，后续真实执行阶段才允许 |
| 允许监听端口使用 | `27939/TCP` |
| 允许生成真实分享链接 | 是，但不得泄露真实链接 |
| 允许写入 `node.share_link` | 是，但仅在创建成功后写入 |
| 允许修改服务器本机 Xray 配置 | 是，但只允许写入 LiveLine 本次生成配置，不覆盖未知已有配置 |
| 当前机器无已有 Xray 配置 | 用户确认，但正式执行前必须再跑 preflight 复核 |
| 失败回滚 | 只清理本次新增内容 |

## 正式执行前强制复核

正式执行前必须重新运行 `landing_preflight`，并确认：

- `27939/TCP` 当前未监听。
- Xray 当前未安装。
- 当前无已有 Xray 配置。
- Worker 仍在线且支持命令通道。
- 云安全组 / 云防火墙 / 服务器本机防火墙仍放行 `27939/TCP`。
- 目标服务器仍为预期落地服务器。

如果任一复核不通过，不得进入正式创建执行。

## `node.share_link` 写入规则

`node.share_link` 只能在后续真实执行阶段满足以下条件后写入：

- Xray-core 安装成功。
- LiveLine 本次生成的 Xray 配置写入成功。
- Xray 配置测试通过。
- Xray 服务启动成功。
- `27939/TCP` 监听成功。
- 节点记录创建成功。
- 真实分享链接生成成功。

真实节点链接不得写入 README、阶段文档、终端日志、任务日志、后端日志、聊天记录或 PR 描述。

## 回滚边界

如果后续真实创建失败，回滚只允许清理本次新增内容：

- 本次新增的 Xray 配置。
- 本次新增的 systemd 服务。
- 本次新增的监听端口状态。
- 本次新增的节点记录或未完成记录。

回滚不得删除非 LiveLine 管理文件，不得删除未知已有配置，不得清理非本次创建的服务，不得修改无关防火墙规则。

## dry-run / execution guard 改动

- 下一阶段建议改为 `Stage 3.3.37-formal-landing-node-create-execution`。
- dry-run 端口固定为 `27939/TCP`。
- 云安全组 / 云防火墙 / 服务器本机防火墙确认项默认反映用户已确认状态。
- 防火墙确认完成时，不再显示“确认不完整”的阻塞项。
- dry-run 仍显示“正式执行前必须重新运行 landing_preflight”。
- dry-run 仍显示“当前未进入正式执行阶段”。
- 前端增加“正式执行保护清单”。

## 本阶段安全边界

本阶段明确不执行：

- 不执行 SSH。
- 不执行远程命令。
- 不连接真实 VPS。
- 不安装 Xray。
- 不写入 Xray 配置。
- 不创建节点。
- 不新增监听端口。
- 不修改云安全组。
- 不修改云防火墙。
- 不修改服务器本机防火墙。
- 不修改 `node.share_link`。
- 不生成真实节点链接。
- 不创建任务。
- 不执行 cutover。
- 不写入真实 token。
- 不写入真实密码。
- 不写入 `SESSION_SECRET` 真实值。
- 不写入 Reality privateKey。
- 不写入完整节点链接。

## 修改文件

- `backend/app/services/landing_node_plan.py`
  - 将下一阶段建议改为 `Stage 3.3.37-formal-landing-node-create-execution`。
  - 增加 `27939/TCP` 固定端口保护。
  - 增加 execution guard 返回内容。
  - 增加正式执行前重新运行 `landing_preflight` 的提示。
- `backend/app/schemas/landing_node_plan.py`
  - 增加 `execution_guard` 响应字段。
- `frontend/lib/api.ts`
  - 增加 `execution_guard` 类型字段。
- `frontend/components/ServerManagementPanel.tsx`
  - 将 dry-run 端口固定为 `27939/TCP`。
  - 默认反映用户已完成防火墙放行确认。
  - 增加“正式执行保护清单”展示。
  - 保持无真实执行按钮。
- `README.md`
  - 增加 Stage 3.3.36 记录。
- `docs/stage-3.3.36-formal-landing-node-create-execution-guard.md`
  - 新增本阶段文档。

## 验收清单

- `git diff --check` 通过。
- `python3 -m compileall backend/app` 通过。
- `docker compose exec -T frontend npm run build` 通过。
- `docker compose up --build -d` 通过。
- `curl -s http://127.0.0.1:8000/api/health` backend / database / redis / worker 全部 ok。
- `curl -I http://127.0.0.1:3000` 返回 HTTP 200。
- Redis `temp_credential:*` 为 0。
- pending / running tasks 为 0。
- 敏感信息扫描通过。

## 阶段结论

Stage 3.3.36 只增加正式创建落地节点前的 execution guard。候选端口固定为 `27939/TCP`，防火墙类确认已由用户完成，但正式执行前仍必须重新运行 `landing_preflight` 并确认端口未监听、Xray 未安装、无已有 Xray 配置。本阶段不执行真实节点创建，不安装 Xray，不新增监听端口，不修改防火墙，不修改 `node.share_link`，不生成真实节点链接，不执行 cutover。
