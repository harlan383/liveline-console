# Stage 3.3.33 Worker Preflight Interface Normalization

## 当前阶段目标

本阶段修复 `landing_preflight` 只读预检结果中的网卡识别和监听端口摘要问题，为后续落地节点创建审批提供更可靠的本地 Go / No-Go 判断。

本阶段不是正式落地节点创建阶段，不执行 SSH / 远程命令，不连接真实 VPS，不安装 Xray / x-ui / 3x-ui，不创建节点，不新增监听端口，不修改 `node.share_link`，不执行 cutover。

## 修改范围

- `worker/cmd/liveline-worker/main.go`
- `worker/cmd/liveline-worker/main_test.go`
- `backend/worker-binaries/liveline-worker-linux-amd64`
- `backend/app/services/landing_node_plan.py`
- `backend/app/services/worker_targeting.py`
- `frontend/components/ServerManagementPanel.tsx`
- `README.md`

## Worker 版本和预检版本

本阶段将 Worker 版本更新为：

```text
0.1.3-stage-3.3.33
```

`landing_preflight` 返回的 `preflight_version` 更新为：

```text
0.2
```

后端 Worker 目标选择也同步要求 `landing_preflight` 使用 `0.1.3-stage-3.3.33` 或更新版本，避免旧 Worker 继续返回混淆的网卡字段。

## 网卡字段规范

本阶段将 Worker 配置网卡和系统默认公网网卡分开返回。

返回字段包括：

| 字段 | 含义 |
| --- | --- |
| `system.worker_config_interface` | Worker 配置文件中的网卡 |
| `system.interface_name` | 兼容旧字段，仍等于 Worker 配置网卡 |
| `network.worker_config_interface` | Worker 配置网卡 |
| `network.default_route_interface` | `ip route show default` 解析出的默认路由网卡 |
| `network.default_route_gateway` | `ip route show default` 解析出的网关 |
| `network.primary_interface` | 当前用于公网判断的主网卡，优先使用默认路由网卡 |
| `network.primary_interface_ip` | 主网卡上的 IPv4 地址 |
| `network.interface_mismatch` | Worker 配置网卡是否与默认路由网卡不一致 |

当前预期真实场景为：

| 项目 | 预期值 |
| --- | --- |
| Worker 配置网卡 | `eth0` |
| 系统默认公网网卡 | `ens17` |
| 默认网关 | `64.90.13.254` |
| 默认公网网卡 IP | `64.90.13.19` |
| 是否不一致 | `true` |

如发现不一致，Worker 会返回结构化 warning：

```json
{
  "code": "interface_mismatch",
  "message": "Worker configured interface eth0 differs from default route interface ens17.",
  "worker_config_interface": "eth0",
  "default_route_interface": "ens17"
}
```

## 监听端口摘要修复

本阶段修复 `ss -lntup` 解析逻辑：

- 只统计有效 TCP `LISTEN` 行。
- 跳过无效本地监听地址。
- 跳过无效端口。
- 不再产生 `port=0`。
- `debug_skipped_count` 记录被跳过的无效监听行数量。

`important_ports` 保持：

- `22`
- `80`
- `443`
- `8443`
- `18443`

当前预期真实状态为：

- `22`：listening
- `80`：not_listening
- `443`：not_listening
- `8443`：not_listening
- `18443`：not_listening
- `listening_count=1`

## 后端 dry-run 计划兼容

`landing_node_plan` 优先读取新字段：

- `network.worker_config_interface`
- `network.default_route_interface`
- `network.default_route_gateway`
- `network.primary_interface`
- `network.primary_interface_ip`
- `network.interface_mismatch`

同时保留旧字段兼容：

- `system.interface_name`
- `network.primary_interface`

如果 Worker 配置网卡与默认路由网卡不一致，dry-run 计划继续返回 No-Go，并保留 `interface_mismatch` 阻塞项。本阶段不自动清除该阻塞项。

## 前端展示

落地服务器只读预检摘要和创建节点 dry-run 计划现在展示：

- Worker 配置网卡
- 系统默认公网网卡
- 默认公网网关
- 默认公网网卡 IP
- 是否不一致
- 有效监听端口
- 监听端口数量
- 重要端口状态

前端不会展示完整节点链接，不会展示 SSH Key、密码、token、SESSION_SECRET、Reality privateKey 或 Worker secret。

## 安全边界

本阶段未执行以下操作：

- 未安装 Xray / x-ui / 3x-ui
- 未安装 socat / gost
- 未执行 SSH / 远程命令
- 未连接真实 VPS
- 未创建节点
- 未创建中转链路
- 未新增监听端口
- 未修改防火墙
- 未修改云安全组
- 未修改 `node.share_link`
- 未生成真实可用完整节点链接
- 未执行正式 cutover
- 未清理旧 Worker 记录或命令

## 验收清单

- `go version`：通过，使用本机 `/usr/local/go/bin/go`。
- `cd worker && go test ./...`：通过。
- `cd worker && go build -o /tmp/liveline-worker ./cmd/liveline-worker`：通过。
- `GOOS=linux GOARCH=amd64 CGO_ENABLED=0 go build`：通过，已更新 `backend/worker-binaries/liveline-worker-linux-amd64`。
- `PYTHONPYCACHEPREFIX=/private/tmp/liveline-pycache python3 -m compileall backend/app`：通过。
- `docker compose exec -T frontend npm run build`：通过。
- `docker compose up --build -d`：通过。
- `http://localhost:3000`：HTTP 200。
- `/api/health`：backend / database / redis / worker 全部 ok。
- Redis `temp_credential:*`：0。
- pending / running tasks：0。
- 敏感信息扫描：通过，仅命中 README 历史通用 `vless://` 说明文字，无真实敏感信息。
