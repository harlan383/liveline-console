# Stage 3.3.37 Formal Landing Node Create Execution

## 本阶段目标

Stage 3.3.37 开发正式创建落地节点的受控执行能力，但本阶段的本地开发、验证、提交、PR 和合并流程本身不执行真实创建。

本阶段新增后端正式创建 API、Worker `landing_node_create` 命令处理、前端二次确认入口和安全文档。真实执行必须由用户在界面完成全部确认后，再由已绑定的 `liveline-worker` 轮询执行。

## 锁定目标

本阶段只允许以下审批对象进入正式创建流程：

| 项目 | 值 |
| --- | --- |
| 目标落地服务器 ID | `968519b3-9017-4b27-a9a0-d5731033f84f` |
| 目标落地服务器 IP | `64.90.13.19` |
| 目标 Worker ID | `ef421476-dcad-4380-8cea-40dc81e543fd` |
| Worker 网卡 | `ens17` |
| 候选监听端口 | `27939/TCP` |

用户已确认：

- 云安全组已放行 `27939/TCP`。
- 云防火墙已放行 `27939/TCP`。
- 服务器本机防火墙已放行 `27939/TCP`。
- 允许安装 Xray-core。
- 允许创建 VLESS Reality 落地节点。
- 允许使用 `27939/TCP` 作为监听端口。
- 允许生成真实分享链接，但不得泄露真实链接。
- 允许在创建成功后写入 `node.share_link`。
- 允许修改服务器本机 Xray 配置，但只允许写入 LiveLine 本次生成配置。
- 当前机器没有已有 Xray 配置，但正式执行前必须再跑 preflight 复核。
- 如果创建失败，允许回滚，但只清理本次新增内容。

## 正式执行前必须复核

即使已有审批，正式执行前仍必须由 Worker 重新执行本机预检：

- 必须重新运行 `landing_preflight`。
- 必须确认 `27939/TCP` 当前未监听。
- 必须确认 `/usr/local/bin/xray` 和 `/usr/bin/xray` 不存在。
- 必须确认 `/usr/local/etc/xray/config.json` 和 `/etc/xray/config.json` 不存在。
- 必须确认 `xray.service`、`x-ui.service`、`3x-ui.service` 不存在。
- 必须确认审批锁定 Worker 在线，且支持 `landing_node_create`。

任何复核失败都必须中止创建，不能写入 `node.share_link`。

## 执行流程

新增后端 API：

- `POST /api/vps/{server_id}/landing-node-create`

该接口必须要求二次确认：

- `approved_port = 27939`
- `confirm_firewall_open = true`
- `confirm_generate_share_link = true`
- `confirm_write_share_link_after_success = true`
- `confirm_no_existing_xray = true`
- `confirm_rollback_new_artifacts_only = true`

后端只会为审批锁定的 Worker 创建 `landing_node_create` 命令。通用 Worker 命令入口不能绕过该 API 直接创建正式命令。

Worker 执行阶段：

1. 重新执行本机 preflight。
2. 下载并安装固定 Xray-core binary。
3. 生成 VLESS UUID、Reality key pair 和 shortId。
4. 写入 LiveLine 管理配置：`/usr/local/etc/liveline-xray/config.json`。
5. 写入 LiveLine 管理 systemd service：`/etc/systemd/system/liveline-xray.service`。
6. 执行 `xray run -test`。
7. `systemctl daemon-reload`、`enable`、`restart`。
8. 验证 service active。
9. 验证 `27939/TCP` 已监听。
10. 在内存中生成真实 `vless://` 分享链接并回传给 backend。
11. backend 只在 Worker 成功结果后写入 `nodes` 和 `node.share_link`。

## share_link 安全要求

- `node.share_link` 只能在创建成功、Xray 服务启动成功、端口监听成功后写入。
- 真实 `vless://` 链接不得写入 README。
- 真实 `vless://` 链接不得写入阶段文档。
- 真实 `vless://` 链接不得写入终端日志。
- 真实 `vless://` 链接不得写入 Worker 日志。
- 真实 `vless://` 链接不得写入 backend 命令结果历史。
- 真实 `vless://` 链接不得写入聊天记录。
- Reality private key 只允许写入本机 Xray 配置，不允许返回 backend。

backend 接收 Worker 成功结果时，会先使用 `secure_share_link` 写入 `nodes.share_link`，然后从 Worker 命令结果中移除完整链接，只保留 `share_link_present` 和 `masked_share_link`。

## 回滚边界

如果正式执行失败，Worker 只能清理本次运行新增的内容：

- 本次新增的 `liveline-xray.service`。
- 本次新增的 LiveLine Xray 配置文件。
- 本次新增的 Xray binary。
- 本次启动的 LiveLine 管理监听。

不得删除或覆盖非 LiveLine 管理文件：

- 不删除未知已有 Xray 配置。
- 不删除用户已有 systemd 服务。
- 不修改云安全组。
- 不修改云防火墙。
- 不修改服务器防火墙。
- 不修改 `node.share_link`。

## 修改范围

- `backend/app/api/routes/vps.py`
- `backend/app/api/routes/workers.py`
- `backend/app/schemas/landing_node_plan.py`
- `backend/app/schemas/worker_commands.py`
- `backend/app/services/landing_node_create.py`
- `backend/app/services/worker_commands.py`
- `backend/app/services/worker_targeting.py`
- `backend/worker-binaries/liveline-worker-linux-amd64`
- `frontend/components/ServerManagementPanel.tsx`
- `frontend/lib/api.ts`
- `worker/cmd/liveline-worker/main.go`
- `README.md`
- `docs/stage-3.3.37-formal-landing-node-create-execution.md`

## 本阶段安全边界

本阶段开发和验证过程中：

- 未执行 SSH。
- 未执行远程命令。
- 未连接真实 VPS。
- 未安装 Xray。
- 未创建节点。
- 未新增监听端口。
- 未修改云安全组 / 云防火墙 / 服务器防火墙。
- 未修改 `node.share_link`。
- 未生成真实节点链接。
- 未执行 cutover。

## 验收清单

- `git diff --check` 通过。
- `python3 -m compileall backend/app` 通过。
- `cd worker && go test ./...` 通过。
- `cd worker && go build -o /tmp/liveline-worker ./cmd/liveline-worker` 通过。
- Linux amd64 Worker binary 已通过本机 Go 交叉编译更新。
- `docker compose exec -T frontend npm run build` 通过。
- `docker compose up --build -d` 通过。
- `curl -s http://127.0.0.1:8000/api/health` 返回 backend / database / redis / worker ok。
- `curl -I http://127.0.0.1:3000` 返回 HTTP 200。
- Redis `temp_credential:*` 为 0。
- pending / running tasks 为 0。
- 敏感信息扫描未发现真实 token、密码、`SESSION_SECRET`、Reality privateKey、完整 `vless://` 节点链接或完整 worker token。

## 结论

Stage 3.3.37 已准备正式创建落地节点的受控执行能力。当前开发阶段仍未执行真实创建；正式执行必须由用户在前端完成二次确认，并由审批锁定的 Worker 在目标服务器上重新预检后执行。
