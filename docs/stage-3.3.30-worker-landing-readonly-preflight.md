# Stage 3.3.30 Worker Landing Readonly Preflight

## 本阶段目标

本阶段为落地服务器 Worker 增加第一版只读环境预检命令：`landing_preflight`。

该命令用于后续真实远程操作前，通过已安装并在线的 `liveline-worker` 在服务器本机执行固定只读检查，返回脱敏结构化结果，帮助判断落地服务器环境是否具备继续进入后续审批阶段的基础条件。

本阶段不是远程执行创建阶段，不创建节点，不创建中转链路，不修改 `node.share_link`，不执行正式 cutover。

## 修改范围

- `backend/app/schemas/worker_commands.py`
  - 新增允许的 command type：`landing_preflight`。
- `backend/app/services/worker_targeting.py`
  - 为不同 command type 增加最低 Worker 版本门槛。
  - `landing_preflight` 要求 Worker 版本不低于 `0.1.2-stage-3.3.30`。
- `backend/app/api/routes/workers.py`
  - 创建 Worker command 时按 command type 解析可用目标 Worker。
  - 当在线 Worker 版本不足时返回 `WORKER_COMMAND_UNSUPPORTED`，不创建 pending command。
- `backend/app/services/worker_commands.py`
  - 为 `landing_preflight` 增加简短 `result_summary`。
- `worker/cmd/liveline-worker/main.go`
  - Worker 版本升级到 `0.1.2-stage-3.3.30`。
  - 新增固定只读检查集合。
- `frontend/lib/api.ts`
  - 前端 command type 类型新增 `landing_preflight`。
- `frontend/components/ServerManagementPanel.tsx`
  - 在线落地服务器新增“只读预检”按钮。
  - 成功结果展示脱敏摘要。
- `frontend/app/globals.css`
  - 增加只读预检摘要样式。
- `README.md`
  - 增加 Stage 3.3.30 范围和状态记录。

## Worker 版本门槛

`landing_preflight` 需要 Worker 支持新的只读预检处理逻辑，因此最低版本为：

```text
0.1.2-stage-3.3.30
```

旧版本 Worker，例如 `0.1.1-stage-3.3.28`，仍可继续处理 `collect_status` 等旧命令，但不会接收 `landing_preflight`。

如果目标服务器只有旧版本 Worker 在线，后端返回：

```text
WORKER_COMMAND_UNSUPPORTED
```

前端会提示用户重新生成安装命令并升级服务器上的 `liveline-worker`。

## 只读检查内容

Worker 只执行固定白名单内的只读检查，不接受前端或后端传入任意 shell 命令。

当前检查范围：

- 系统信息：hostname、OS、架构、当前用户、Worker 版本。
- 网络信息：主机名、IP 列表、默认路由摘要。
- 监听端口：`ss -lntup` 的摘要和关键端口状态。
- 服务状态：`xray`、`liveline-worker` 等服务的 active / enabled / status 摘要。
- 二进制存在性：`xray`、`socat`、`gost` 等命令是否存在。
- 防火墙摘要：`ufw status`、`firewall-cmd --state`、`iptables -S` 的只读摘要。
- Xray 文件发现：仅检查路径是否存在和文件元数据，不读取完整配置内容。
- warnings / errors：只记录脱敏的预检警告和错误摘要。

## result_json 字段

`worker_commands.result_json` 会保存结构化结果，主要包含：

- `preflight_version`
- `worker_version`
- `timestamp`
- `system`
- `network`
- `ports`
- `services`
- `binaries`
- `firewall`
- `xray_discovery`
- `warnings`
- `errors`

结果用于本地控制台展示摘要，不写入完整节点链接、真实密钥、真实 token 或完整敏感配置。

## 安全边界

本阶段明确禁止：

- 不读取完整 Xray 配置。
- 不返回 Reality privateKey。
- 不返回完整节点链接。
- 不返回 UUID、token、cookie、session 或真实密码。
- 不执行 SSH。
- 不执行 Codex 到远程服务器的命令。
- 不接受任意 shell payload。
- 不创建节点。
- 不创建中转链路。
- 不新增监听端口。
- 不修改防火墙。
- 不修改 `node.share_link`。
- 不执行正式 cutover。
- 不新增数据库迁移。

## 验收清单

- `go test ./...`：通过。
- `go build -o /tmp/liveline-worker ./cmd/liveline-worker`：通过。
- Linux Worker binary rebuild：通过，`backend/worker-binaries/liveline-worker-linux-amd64` 已重新生成。
- `python3 -m compileall backend/app`：本机默认 pycache 路径被 macOS sandbox 拒绝；使用 `-X pycache_prefix=/private/tmp/liveline-pycache` 通过，容器内 `python -m compileall app` 通过。
- `docker compose exec -T frontend npm run build`：通过。
- `docker compose up --build -d`：通过。
- `/api/health`：backend / database / redis / worker 全部 ok。
- Redis `temp_credential:*`：0。
- pending / running tasks：0。
- `git diff --check`：通过。
- 本地 target selection 自检：通过，旧版 Worker 返回 `WORKER_COMMAND_UNSUPPORTED`，新版 Worker 可接收 `landing_preflight`。
- 敏感信息扫描：通过，仅命中 `.env.example` 占位符和代码变量名 `worker_secret`，未发现真实密钥、密码、token 或完整节点链接。

## 阶段结论

Stage 3.3.30 增加落地服务器只读预检命令能力，并保持当前系统安全边界。

本阶段未新增数据库迁移，未新增监听端口，未修改 `node.share_link`，未执行 SSH / 远程命令，未创建节点，未创建中转链路，未执行正式 cutover。
