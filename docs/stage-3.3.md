# Stage 3.3 香港服务器模拟中转

Stage 3.3 将使用普通公网中转服务器模拟未来 IEPL / IPLC 中转链路。Stage 3.3.1 只实现“中转服务器只读检查”。Stage 3.3.2 只实现“安装 gost binary”。当前阶段仍不创建转发规则，不连接落地 VPS，不生成真实中转链接。

## Stage 3.3.1 已实现范围

- 新增 `read_transit_server` task type。
- 新增 `POST /api/transit-resources/{id}/read-server`。
- 仅允许读取 `resource_type=server`、`status=active`、`has_ssh=true` 的中转资源。
- 写接口需要管理员登录、CSRF 和 `multipart/form-data`。
- SSH Key / Passphrase 只进入 Redis 临时加密凭据。
- RQ job 参数只包含 `task_id`、`transit_resource_id`、`temp_credential_id`。
- Worker 读取 Redis 凭据后立即删除。
- 结果写入 `tasks.result_data`，步骤写入 `task_logs`。
- 前端在中转资源详情中新增“读取中转服务器”区域。
- 前端展示只读检查任务状态、日志、系统信息、工具状态、端口和防火墙只读摘要。

## 只读检查内容

- 系统版本：`cat /etc/os-release`
- 架构：`uname -m`
- 当前用户：`whoami`
- systemd 是否可用：`test -d /run/systemd/system`
- 工具是否存在：`command -v gost`、`command -v nginx`、`command -v socat`、`command -v xray`
- TCP 监听端口：`ss -ltnH`
- 防火墙状态：`ufw status`、`iptables -S`、`firewall-cmd --state`

每条命令都必须通过 SSH 只读执行并设置 timeout。命令输出会脱敏，`task_logs` 不记录原始敏感内容。

## result_data

`read_transit_server` 成功或发现只读问题时写入：

- `classification=read_transit_server`
- `checked`
- `passed`
- `message`
- `ssh.username`
- `ssh.ssh_key_fingerprint`
- `ssh.host_key_fingerprint`
- `system`
- `tools`
- `ports`
- `firewall`
- `warnings`
- `failures`

`result_data` 不包含 SSH 私钥、Passphrase、Cookie、数据库连接串、完整配置文件或任何节点私钥。

## task_logs

标准步骤：

- `queued`
- `load_credentials`
- `read_transit_server`
- `ssh_connect`
- `read_system`
- `check_tools`
- `check_ports`
- `check_firewall`
- `save_result`
- `complete`

## 安全边界

- SSH Key / Passphrase 只能通过 Redis 临时加密凭据传递。
- RQ job 不得携带 SSH Key / Passphrase。
- Worker 读取凭据后必须删除 Redis 凭据。
- 本阶段不新增数据库表。
- 本阶段不新增 Alembic。
- 本阶段不新增 `transit_routes` 或 `forwarding_rules`。
- 本阶段不修改 `nodes`、`vps_servers` 或现有直连节点。

## 禁止范围

- 不连接落地 VPS。
- 不安装 `gost` / `nginx` / `socat` / Xray `dokodemo-door`。
- 不配置转发。
- 不创建中转路由。
- 不生成真实中转链接。
- 不生成二维码。
- 不修改 Xray 配置。
- 不修改防火墙。
- 不开放端口。
- 不写 iptables。
- 不执行 `apt` / `yum` / `dnf`。
- 不执行 `curl | bash` 或 `wget` 安装命令。
- 不执行 `chmod`、`cp`、`mv`、`rm`、`tee`、`sed` 等写入或修改命令。
- 不执行 `systemctl start` / `stop` / `restart` / `enable`。
- 不调用 3x-ui。
- 不做真实中转连通性测试。
- 不做流量统计自动采集。
- 不做自动测速。

## Stage 3.3.1 冻结结论

Stage 3.3.1 已通过真实香港中转服务器只读验收并冻结。`read_transit_server` 任务执行成功，系统确认可以通过 SSH 登录香港中转服务器，并完成只读环境检查。本阶段没有安装工具、没有配置转发、没有修改防火墙、没有写 iptables、没有连接落地 VPS，也没有影响当前 active 直连节点。

冻结依据：

- task status 为 `success`。
- `classification=read_transit_server`。
- 当前步骤为 `complete`。
- 系统为 Debian GNU/Linux 12。
- 架构为 `x86_64`。
- `whoami=root`。
- `root=true`。
- `systemd_available=true`。
- 已读取 TCP 监听端口，当前监听端口包含 `20575`。
- `gost` 未安装。
- `nginx` 未安装。
- `socat` 未安装。
- `xray` 未安装。
- `ufw` / `iptables` / `firewalld` 均未启用或不可用，仅作为只读状态记录。
- `task_logs` 10 步完整：`queued`、`load_credentials`、`read_transit_server`、`ssh_connect`、`read_system`、`check_tools`、`check_ports`、`check_firewall`、`save_result`、`complete`。
- Redis `temp_credential:*` 已清理。
- 未泄露 SSH 私钥、Passphrase、Cookie 或数据库连接串。
- 未安装 `gost` / `nginx` / `socat` / `xray`。
- 未配置转发。
- 未修改防火墙。
- 未写 iptables。
- 未连接落地 VPS。
- 未修改当前 active 直连节点。
- 未生成中转链接。

重要提醒：

- 早期验收记录曾显示香港中转服务器资源的 SSH 端口为 `20575`。
- Stage 3.3.3-fix-a 复验前已确认该端口配置是资源 SSH 端口错配；正式接受的 SSH 端口为 `22`。
- 后续创建中转转发时仍不要直接复用历史问题端口 `20575`，应单独评审并选择确认空闲的监听端口。

冻结后边界：

- 后续不得随意修改 `read_transit_server` 核心流程。
- 后续不得随意修改只读命令清单。
- 后续不得放宽 Redis 临时凭据边界。
- 后续不得在 Stage 3.3.1 范围内加入安装、配置转发、改防火墙、写 iptables、连接落地 VPS 或生成中转链接行为。

## Stage 3.3.2 已实现范围

Stage 3.3.2 只安装 gost binary，并验证 gost 版本。本阶段不创建转发规则、不创建 gost 转发 systemd service、不监听任何新端口、不连接落地 VPS、不生成中转链接。

已实现：

- 新增 `install_gost` task type。
- 新增 `POST /api/transit-resources/{id}/install-gost`。
- 仅允许 `resource_type=server`、`status=active`、`has_ssh=true` 的中转资源使用。
- 写接口需要管理员登录、CSRF 和 `multipart/form-data`。
- 必须重新上传或粘贴 SSH Key，Passphrase 可选。
- SSH Key / Passphrase 只进入 Redis 临时加密凭据。
- RQ job 参数只包含 `task_id`、`transit_resource_id`、`temp_credential_id`。
- Worker 读取 Redis 凭据后立即删除。
- 固定 gost 版本为 `v3.2.6`。
- 固定官方 release 下载地址：
  `https://github.com/go-gost/gost/releases/download/v3.2.6/gost_3.2.6_linux_amd64.tar.gz`
- 固定 sha256：
  `b39037b0380ea001fb3c0c28441c2e10bfc694f90682739a65b53e55dce5238b`
- Worker 本地下载官方 release 并完成 sha256 校验。
- Worker 通过 SFTP 上传校验后的 gost binary 到远端临时路径。
- 远端安装到 `/usr/local/bin/gost`。
- 安装后执行 `test -x /usr/local/bin/gost` 和 `/usr/local/bin/gost -V`。
- 结果写入 `tasks.result_data`。
- 步骤写入 `task_logs`。
- 前端中转资源详情新增“安装 gost”区域，展示任务状态、日志、安装结果和 gost version。

## Stage 3.3.2 安装前检查

Worker 必须检查：

- `cat /etc/os-release`
- `uname -m`
- `whoami`
- `test -d /run/systemd/system`
- `command -v gost`
- `test -d /usr/local/bin`
- `test -w /usr/local/bin`
- `ss -ltnH`
- 是否 root。
- 架构是否为 `x86_64`。
- systemd 是否可用。
- `20575` 是否被监听，并记录历史问题端口 warning：后续不得直接作为中转监听端口。

如果 `command -v gost` 已存在：

- 不下载。
- 不覆盖。
- 不升级。
- 只读取版本。
- 返回 `already_installed=true`。

## Stage 3.3.2 允许命令与远端行为

允许的远端命令：

- `cat /etc/os-release`
- `uname -m`
- `whoami`
- `test -d /run/systemd/system`
- `command -v gost`
- `/usr/local/bin/gost -V`
- `test -d /usr/local/bin`
- `test -w /usr/local/bin`
- `test -x /usr/local/bin/gost`
- `ss -ltnH`
- `install -m 0755 <tmp_gost> /usr/local/bin/gost`

允许通过 SFTP 上传和清理本任务创建的临时 gost 文件。

## Stage 3.3.2 禁止范围

- 不创建转发规则。
- 不创建 gost 转发 systemd service。
- 不监听任何新端口。
- 不连接落地 VPS。
- 不修改落地 VPS。
- 不修改当前 active 直连节点。
- 不修改 Xray 配置。
- 不安装 `nginx`。
- 不安装 `socat`。
- 不安装 `xray`。
- 不配置 Xray `dokodemo-door`。
- 不修改防火墙。
- 不开放端口。
- 不写 iptables。
- 不调用 3x-ui。
- 不生成中转链接。
- 不生成二维码。
- 不做真实连通性测试。
- 不做流量统计。
- 不做自动测速。
- 不新增 `transit_routes` 表。
- 不新增 `forwarding_rules` 表。
- 不新增 Alembic。
- 不新增数据库字段。
- 不覆盖已有 gost。
- 不使用 `latest`。
- 不使用 `curl | bash`。

## Stage 3.3.2 冻结结论

Stage 3.3.2 已通过真实香港中转服务器安装验收并冻结。本阶段只在香港中转服务器上安装 gost binary，并验证 gost 版本；没有创建转发规则、没有创建 systemd 转发服务、没有监听新端口、没有连接落地 VPS，也没有生成中转链接。

冻结依据：

- docker compose 5 个容器运行正常。
- `/api/health` 返回 backend、database、redis、worker 全部 `ok`。
- Alembic 仍为 `0005_transit_defaults`。
- `POST /api/transit-resources/{resource_id}/install-gost` 已出现在 OpenAPI。
- 未新增 `transit_routes` 表。
- 未新增 `forwarding_rules` 表。
- 未新增 `create_transit_route` API。
- 未新增生成中转链接 API。
- Redis `temp_credential:*` 为 0。
- pending / running tasks 为 0。
- `npm audit` 为 `found 0 vulnerabilities`。
- 当前 active 节点数量仍为 1。
- 目标 `transit_resource` 满足 `server` + `has_ssh` + `active`。
- gost 安装前未安装。
- 第一次 `install_gost` 任务成功：`task_id=432e9e20-7ee5-40cd-9fda-f95f536cc55d`。
- 第一次任务 `classification=install_gost`、`installed=true`、`already_installed=false`、`failures=[]`。
- 安装路径为 `/usr/local/bin/gost`。
- gost 版本为 `gost v3.2.6`。
- `sha256_verified=true`。
- `download_url` 指向固定 GitHub official release。
- 系统检查结果包含 `whoami=root`、`architecture=x86_64`、`systemd_available=true`。
- `task_logs` 12 步完整：`queued`、`load_credentials`、`install_gost`、`ssh_connect`、`preflight`、`check_existing_gost`、`download_gost`、`verify_download`、`install_binary`、`verify_gost`、`save_result`、`complete`。
- 香港服务器直接验证通过：`command -v gost` 返回 `/usr/local/bin/gost`，`gost -V` 返回 `gost v3.2.6`，`test -x /usr/local/bin/gost` 通过。
- 安装前后监听端口数量不变，`9 ports -> 9 ports`。
- xray 保持 active。
- 没有 `gost-forward` systemd 服务。
- 第二次 `install_gost` 任务成功：`task_id=625ae88a-7200-4398-a165-10d0d5f2e97d`。
- 第二次任务返回 `installed=true`、`already_installed=true`，不下载、不覆盖、不升级，只读取版本。
- Redis 临时凭据已清理。
- pending / running tasks 为 0。
- `task_logs` 未泄露 SSH 私钥、Passphrase、Cookie、数据库连接串、落地 VPS 连接信息或任何转发配置内容。
- `result_data` 未包含 SSH 私钥或 Passphrase。
- 数据库未保存 SSH Key 或香港服务器密码。
- backend / worker 日志无敏感信息，无 traceback。
- 当前 active 直连节点数量仍为 1。
- `nodes` 表未变化。
- `vps_servers` 表未变化。

Stage 3.3.2 最终允许范围：

- 安装 gost binary。
- 固定 gost `v3.2.6`。
- 固定官方 release `download_url`。
- 固定 sha256 校验。
- 安装到 `/usr/local/bin/gost`。
- 验证 `/usr/local/bin/gost` 可执行。
- 验证 `gost -V`。
- 如果已安装 gost，则返回 `already_installed=true`。
- 不覆盖已有 gost。
- 不升级已有 gost。
- 写入 `tasks.result_data`。
- 写入 `task_logs`。
- Redis 临时凭据任务完成后删除。

Stage 3.3.2 最终禁止范围：

- 不创建转发规则。
- 不创建 `gost-forward` systemd service。
- 不监听任何新端口。
- 不连接落地 VPS。
- 不修改落地 VPS。
- 不修改当前 active 直连节点。
- 不修改 Xray 配置。
- 不安装 `nginx`。
- 不安装 `socat`。
- 不安装 `xray`。
- 不配置 Xray `dokodemo-door`。
- 不修改防火墙。
- 不开放端口。
- 不写 iptables。
- 不调用 3x-ui。
- 不生成中转链接。
- 不生成二维码。
- 不做真实连通性测试。
- 不做流量统计。
- 不做自动测速。
- 不新增 `transit_routes` 表。
- 不新增 `forwarding_rules` 表。
- 不新增 Alembic。
- 不新增转发规则 API。
- 不新增中转链接 API。
- 不使用 `latest`。
- 不使用 `curl | bash`。
- 不保存 SSH Key。
- 不保存香港服务器密码。

重要提醒：

- Stage 3.3.2 只安装 gost binary。
- 真正创建转发规则必须放到 Stage 3.3.3 单独评审和开发。
- 后续不得随意修改 `install_gost`、固定版本、SHA256 校验、`already_installed` 逻辑，以及“不创建转发”的安全边界。

## Stage 3.3.3 已实现范围

Stage 3.3.3 只实现“创建单条 gost TCP 转发规则”。它会在香港中转服务器上创建一个 systemd service，让客户端通过香港中转服务器的 `listen_port` 转发到现有落地 VPS 的 active Reality 节点端口。

链路：

`client -> 香港中转服务器:listen_port -> 落地 VPS IP:node_port -> 现有 Xray Reality 节点 -> platform`

已实现：

- 新增 `transit_routes` 表。
- 新增 Alembic 迁移 `0006_create_transit_routes`。
- 新增 `TransitRoute` model。
- 新增 `POST /api/transit-routes`。
- 新增 `GET /api/transit-routes`。
- 新增 `GET /api/transit-routes/{id}`。
- 新增 `create_transit_route` task type。
- 复用 Redis 临时加密 SSH 凭据。
- RQ job 参数只包含 `task_id`、`transit_resource_id`、`node_id`、`temp_credential_id` 和非敏感转发参数。
- Worker 只连接香港中转服务器，不连接落地 VPS。
- Worker 校验 `/usr/local/bin/gost` 和 `gost -V`。
- Worker 校验 `listen_port` 不是 `20575`，且未被 `ss -ltnH` 检测为已监听。
- Worker 写入一个 systemd service 文件到 `/etc/systemd/system/liveline-transit-{route_id}.service`。
- Worker 执行 `systemctl daemon-reload`、`systemctl enable`、`systemctl start`。
- Worker 验证 service active 和 `listen_port` LISTEN。
- Worker 生成中转版 `vless://` share link。
- Worker 成功后写入 `transit_routes`。
- Worker 写入 `tasks.result_data` 和 `task_logs`。
- 前端新增“创建单条 gost 转发”入口，展示风险确认、任务状态、任务日志和中转版 link。

## Stage 3.3.3 transit_routes 字段

`transit_routes` 包含：

- `id`
- `name`
- `transit_resource_id`
- `node_id`
- `landing_vps_id`
- `listen_port`
- `target_host`
- `target_port`
- `forwarding_method`
- `service_name`
- `service_path`
- `status`
- `share_link`
- `created_at`
- `updated_at`
- `deleted_at`

本阶段 `forwarding_method` 只允许 `gost`。`status` 首版使用 `active` / `error`，预留 `disabled` 给后续删除 / 停用阶段。

## Stage 3.3.3 gost 与 systemd 设计

Stage 3.3.3 固定使用 `/usr/local/bin/gost`。gost v3.2.6 TCP 转发命令使用：

`/usr/local/bin/gost -L=tcp://0.0.0.0:{listen_port}/{target_host}:{target_port}`

该语法基于 GOST v3 CLI 的 TCP port forwarding `-L` 形式。本阶段直接写入 systemd `ExecStart`，不引入额外 gost 配置文件。

service 示例：

```ini
[Unit]
Description=LiveLine Transit Route {route_id}
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/gost -L=tcp://0.0.0.0:{listen_port}/{target_host}:{target_port}
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

## Stage 3.3.3 中转版 share_link

中转版 link 基于原 active node 的 Reality 参数重新构造：

- address 改为 `transit_resource.entry_host`。
- port 改为 `listen_port`。
- `uuid` 保持原 node `uuid`。
- `flow` 保持原 node `flow`。
- `sni` 保持原 node `sni`。
- `fp` 保持原 node `fingerprint`。
- `pbk` 保持原 node `reality_public_key`。
- `sid` 保持原 node `reality_short_id`。
- `type=tcp`。
- `security=reality`。
- `encryption=none`。

本阶段不修改原 node，不修改原 `node.share_link`，不返回或保存 Reality privateKey。

## Stage 3.3.3 回滚

如果远端创建失败，Worker 会尝试：

- `systemctl stop liveline-transit-{route_id}.service`
- `systemctl disable liveline-transit-{route_id}.service`
- 删除 `/etc/systemd/system/liveline-transit-{route_id}.service`
- `systemctl daemon-reload`

如果数据库写入失败，Worker 也会尝试清理远端 service，避免孤儿转发。回滚失败时，`tasks.result_data.manual_cleanup_required=true`，并记录 `service_name` 与 `service_path` 供人工处理。

## Stage 3.3.3 禁止范围

- 不做删除转发规则。
- 不做批量转发。
- 不做多节点中转。
- 不做二维码。
- 不自动开放防火墙。
- 不写 iptables。
- 不调用 3x-ui。
- 不安装 `nginx` / `socat` / `xray`。
- 不配置 Xray `dokodemo-door`。
- 不连接落地 VPS。
- 不修改落地 VPS。
- 不修改落地 VPS Xray 配置。
- 不重启落地 VPS Xray。
- 不修改原 node。
- 不修改原 `node.share_link`。
- 不修改 `vps_servers`。
- 不做 IEPL 真实验收功能。
- 不做流量统计。
- 不做自动测速。
- 不做负载均衡。
- 不允许 `listen_port=20575`。
- 不允许使用已占用端口。
- 不允许覆盖已有 `liveline-transit` service。
- 不允许使用非 `gost` 转发方式。

重要提醒：

- `20575` 曾被错误配置为香港中转服务器 SSH 端口，后续已修正为 `22`。
- Stage 3.3.3 仍不应直接使用 `20575` 作为中转监听端口，除非后续单独评审确认该端口空闲且适合使用。
- 本系统不自动开放云安全组；创建转发后，用户需要在云厂商后台手动确认监听端口已放行。
- Stage 3.3.3 开发完成后等待真实验收。Codex 本轮不得连接香港服务器、不得上传 SSH Key、不得触发 `create_transit_route`。

## Stage 3.3.3-fix-a 已实现范围

Stage 3.3.3-fix-a 只实现“socat 安装/检查”。本阶段用于为后续 socat 透明 TCP 转发排障做准备，不创建 socat 转发规则，不监听新端口，不修改现有 gost route。

已实现：

- 新增 `install_socat` task type。
- 新增 `POST /api/transit-resources/{id}/install-socat`。
- 仅允许 `resource_type=server`、`status=active`、`has_ssh=true` 且 SSH 元数据完整的中转资源使用。
- 写接口需要管理员登录、CSRF 和 `multipart/form-data`。
- 必须重新上传或粘贴 SSH Key，Passphrase 可选。
- SSH Key / Passphrase 只进入 Redis 临时加密凭据。
- RQ job 参数只包含 `task_id`、`transit_resource_id`、`temp_credential_id`。
- Worker 读取 Redis 凭据后立即删除。
- Worker SSH 登录香港中转服务器后执行安装前检查。
- 如果 `command -v socat` 已存在，则不重复安装，返回 `already_installed=true` 并读取版本。
- 如果 socat 未安装，Debian / Ubuntu 上使用 `apt-get update` 和 `apt-get install -y socat` 安装。
- 安装后执行 `command -v socat` 和 `socat -V` 验证。
- 结果写入 `tasks.result_data`。
- 步骤写入 `task_logs`。
- 前端中转资源详情新增“安装/检查 socat”区域，展示任务状态、日志、socat path/version。

## Stage 3.3.3-fix-a 安装前检查

Worker 检查：

- `cat /etc/os-release`
- `uname -m`
- `whoami`
- `test -d /run/systemd/system`
- `command -v socat`
- `command -v apt-get`
- `ss -ltnH`
- 是否 root。
- 系统是否 Debian / Ubuntu。

## Stage 3.3.3-fix-a 允许命令与远端行为

允许的远端只读命令：

- `cat /etc/os-release`
- `uname -m`
- `whoami`
- `test -d /run/systemd/system`
- `command -v socat`
- `command -v apt-get`
- `ss -ltnH`
- `socat -V`

允许的远端写操作仅限：

- `DEBIAN_FRONTEND=noninteractive apt-get update`
- `DEBIAN_FRONTEND=noninteractive apt-get install -y socat`

除上述 apt 操作外，本阶段不得写配置、不得启动服务、不得监听端口。

## Stage 3.3.3-fix-a result_data

`install_socat` 成功或失败时写入：

- `classification=install_socat`
- `installed`
- `already_installed`
- `message`
- `socat.path`
- `socat.version`
- `system.id`
- `system.name`
- `system.version_id`
- `system.architecture`
- `system.whoami`
- `system.is_root`
- `system.systemd_available`
- `warnings`
- `failures`

`result_data` 不包含 SSH 私钥、Passphrase、Cookie、数据库连接串、完整 `vless://`、Reality privateKey 或任何转发配置内容。

## Stage 3.3.3-fix-a task_logs

标准步骤：

- `queued`
- `load_credentials`
- `install_socat`
- `ssh_connect`
- `preflight`
- `check_existing_socat`
- `install_package`
- `verify_socat`
- `save_result`
- `complete`

## Stage 3.3.3-fix-a 禁止范围

- 不创建 socat 转发规则。
- 不监听新端口。
- 不创建 socat systemd 转发服务。
- 不修改现有 gost route。
- 不删除 gost route。
- 不修改 `transit_routes` active 记录。
- 不生成新的中转链接。
- 不生成二维码。
- 不修改落地 VPS。
- 不修改落地 VPS Xray。
- 不重建 Reality 节点。
- 不修改原 node。
- 不修改原 `node.share_link`。
- 不修改防火墙。
- 不开放端口。
- 不写 iptables。
- 不调用 3x-ui。
- 不做流量统计。
- 不做自动测速。
- 不做负载均衡。
- 不新增 `transit_routes` 表结构。
- 不新增 `forwarding_rules` 表。
- 不新增 Alembic。

重要提醒：

- Stage 3.3.3-fix-a 只安装/检查 socat。
- Stage 3.3.3-fix-b 才能单独评审并开发 socat `2083 -> 74.211.97.116:443` 测试转发。
- Codex 本轮不得连接香港服务器、不得上传 SSH Key、不得触发 `install_socat`。

## Stage 3.3.3-fix-a 真实验收通过结论

Stage 3.3.3-fix-a 已完成真实香港中转服务器 `socat` 安装/检查验收并通过。本阶段只安装/检查 `socat`，没有创建 `socat` 转发规则，没有监听新端口，没有新增 `forwarding_rules`，没有修改现有 gost route，没有修改 `transit_routes.active`，没有修改落地 VPS / Xray / 防火墙 / iptables / `node.share_link`。

正式接受的验收对象：

- `resource_id=6d67c275-8ac9-4775-9519-c89b50718157`
- `name=香港中转服务器`
- `ssh_host=163.223.216.108`
- `ssh_port=22`
- `ssh_username=root`

成功任务：

- `task_id=12ab7383-58c8-4eaa-9f38-68f313d59c59`
- `task_type=install_socat`
- final status 为 `success`
- `current_step=complete`
- `progress=100`
- `already_installed=false`
- `socat.path=/usr/bin/socat`
- `socat.version=socat by Gerhard Rieger and contributors - see www.dest-unreach.org`

验收结论：

- `result_data` 已生成。
- `task_logs` 步骤完整：`queued`、`load_credentials`、`install_socat`、`ssh_connect`、`preflight`、`check_existing_socat`、`install_package`、`verify_socat`、`save_result`、`complete`。
- Redis `temp_credential:*` 最终数量为 0。
- pending / running tasks 最终数量为 0。
- 未发现 SSH Key / Passphrase / `private_key` 泄露。
- 未新增 `forwarding_rules`。
- 未新增 `socat` 转发规则。
- 未新增转发类 task。
- 未修改 `transit_routes.active`。
- 未修改现有 gost route。
- 未修改落地 VPS / Xray / 防火墙 / iptables / `node.share_link`。
- `/api/health` 返回 backend、database、redis、worker 全部 `ok`。

前置问题记录：

- 早前失败原因是目标中转资源的 `ssh_port` 错配为 `20575`。
- Worker 容器 TCP 检查显示 `163.223.216.108:22` 可返回 SSH banner，而 `20575` 无 SSH banner。
- 将正式验收资源 `6d67c275-8ac9-4775-9519-c89b50718157` 的 SSH 端口修正为 `22` 后，`install_socat` 真实验收通过。

重复资源提醒：

- 当前仍存在至少两个指向同一香港中转服务器的资源记录：`6d67c275-8ac9-4775-9519-c89b50718157` 与 `6b53e9bc-946a-4579-94aa-9bd19634cd78`。
- 本阶段不删除任何资源。
- 后续进入 Stage 3.3.3-fix-b 前，建议计划评审中确认是否清理、禁用或合并重复中转资源，避免误选资源触发任务。

Stage 3.3.3-fix-a 通过后的边界：

- 后续不得随意修改 `install_socat`、SSH 连接失败收尾、Redis 临时凭据处理、`socat` 安装/检查命令清单和“不创建转发”的安全边界。
- SSH Key / Passphrase 仍只能通过 Redis 临时加密凭据传递，禁止落库，禁止写入 task logs、backend logs 或 worker logs。
- 自动创建 `socat` 转发规则仍被禁止；Stage 3.3.3-fix-b 必须先单独计划评审。

## Stage 3.3.4-d 真实重启验收通过结论

Stage 3.3.4-d 已完成 `socat` 测试链路受控重启真实验收并通过。本阶段只允许对 `hk-socat-test-18443` 测试链路执行白名单重启与只读校验，不允许作用于 `hk-gost-test-8443` 正式链路，不允许停止、删除、创建线路，不允许修改防火墙、iptables / nft、落地 VPS、Xray 配置或 `node.share_link`。

本次验收对象：

- `task_id=25fcb0c8-2912-4073-bde5-897061672fb6`
- `route_id=97fe351d-d5e6-4684-a37f-4a00b90b4e1e`
- `service_name=liveline-socat-97fe351dd5e64684a37f4a00b90b4e1e.service`
- `route_name=hk-socat-test-18443`
- `method=socat`
- `listen=163.223.216.108:18443`
- `target=74.211.97.116:443`

验收结果：

- final status 为 `success`。
- `current_step=complete`。
- `progress=100`。
- `restart_result=true`。
- `service_status=true`。
- `listen_check=true`。
- `target_connectivity=true`。
- Redis `temp_credential:*` 最终数量为 0。
- pending / running tasks 最终数量为 0。
- `/api/health` 返回 backend、database、redis、worker 全部 `ok`。
- 未发现 SSH Key / Passphrase / `private_key` 泄露。
- 未影响 gost 8443，`hk-gost-test-8443` 仍为 `active`。
- 未修改 `node.share_link`。
- 未新增或删除 route。
- 当前 routes 仍为 2 条：gost 8443 和 socat 18443 均为 `active`。

route_id 更正：

- 早前页面记录中曾出现 `97fe351d-d5e6-4648-a37f-4a00b90b4e1e`。
- 数据库和真实验收确认的实际 route_id 为 `97fe351d-d5e6-4684-a37f-4a00b90b4e1e`。

Stage 3.3.4-d 通过后的边界：

- `restart-socat` 只允许作用于 `forwarding_method=socat` 且 `listen_port=18443` 的测试链路。
- `restart-socat` 禁止作用于 gost 8443 正式链路。
- 禁止执行 `kill`、`pkill`、`iptables`、`nft` 或防火墙修改。
- 禁止停止、删除、创建线路。
- 禁止修改现有 gost 8443。
- 禁止修改现有 socat 18443 配置。
- 禁止修改 `node.share_link`。
- SSH Key / Passphrase 仍只能通过 Redis 临时加密凭据传递，禁止落库，禁止写入 task logs、backend logs 或 worker logs。

## Stage 3.3.4-e 客户端连通性验收通过结论

Stage 3.3.4-e 已完成 `socat` 18443 测试链路客户端连通性验收并通过。本阶段验证的是测试链路可用性，不代表已经完成正式 cutover；当前 gost 8443 仍保留，未被替换，`node.share_link` 未修改。

本次验收对象：

- 测试链路：`hk-socat-test-18443`
- 中转入口：`163.223.216.108:18443`
- 转发方式：`socat`
- 落地目标：`74.211.97.116:443`
- 客户端：Shadowrocket / Reality 节点复制测试

客户端测试方法：

- 复制原直连 Reality 节点一份。
- 仅将 `server` 改为 `163.223.216.108`。
- 仅将 `port` 改为 `18443`。
- `UUID`、`flow`、`reality`、`sni`、`publicKey`、`shortId`、`fingerprint`、`spiderX` 等 Reality 参数全部保持原样。

验收结果：

- Shadowrocket 客户端通过 `163.223.216.108:18443` 中转链路可以正常上网。
- 本地连通性测试 `nc -vz 163.223.216.108 18443` 已通过，结果为 `succeeded`。
- `socat` 18443 Reality 链路已验证可用。
- gost 8443 仍保留，未切换。
- `node.share_link` 未修改。
- 当前只是测试链路通过，不代表已经完成正式 cutover。

Stage 3.3.4-e 通过后的边界：

- `socat` 18443 已验证可用，但仍是测试链路。
- 后续如需切换正式链路，必须单独进入 cutover 阶段计划评审和授权。
- cutover 前不得修改 gost 8443。
- cutover 前不得修改 `transit_routes.active`。
- cutover 前不得修改 `node.share_link`。
- cutover 前不得删除 gost route。
- cutover 前不得把 `socat` 18443 直接设为正式线路。

## Cutover 方案 A 前端验收通过结论

Cutover 方案 A 已完成前端展示增强验收并通过。本方案是低风险前端展示方案，只在“单条转发 -> 中转线路管理”中展示并复制 `socat` 18443 派生测试链接；不写数据库，不替换正式节点链接，不修改 `transit_routes`，不触发任务，不连接服务器，不执行远端命令。

前端验收结果：

- 页面样式已恢复正常。
- 顶部黄色 Cutover 状态提示存在。
- `socat` 18443 显示：`测试可用链路 / 待正式 cutover`。
- `gost` 8443 显示：`回退链路 / 保留`。
- `socat` 18443 卡片有“socat 测试链接”区域。
- 点击“复制 socat 中转测试链接”会弹确认框。
- 确认后复制成功。
- 复制出的链接 `server` 为 `163.223.216.108`。
- 复制出的链接 `port` 为 `18443`。
- 导入 Shadowrocket 成功，并能正常上网。

只读确认结果：

- `node.share_link` 未修改。
- 当前 active node 为 `direct-reality-recreated`。
- `node.share_link` 为 present，长度为 252；验收未输出完整链接。
- 当前有效 routes 仍为 2 条：
  - `hk-gost-test-8443 / gost / 8443 / active`
  - `hk-socat-test-18443 / socat / 18443 / active`
- 没有新增或删除 route。
- 没有触发新 task。
- 最新 task 仍是 `restart_socat_route / success / 2026-06-04 14:30:48+00`。
- pending / running tasks 为 0。
- Redis `temp_credential:*` 为 0。
- `/api/health` 返回 backend、database、redis、worker 全部 `ok`。
- Alembic 仍为 `0006_create_transit_routes`。
- 未发现副作用。

Cutover 方案 A 通过后的边界：

- 方案 A 只允许前端派生和复制 `socat` 18443 测试链接。
- 方案 A 不允许写 `node.share_link`。
- 方案 A 不允许修改 `transit_routes.active`。
- 方案 A 不允许删除 gost route。
- 方案 A 不允许直接把 `socat` 18443 设为正式线路。
- 方案 B / C 必须单独计划评审并获得明确授权。
- 当前仍未正式 cutover。

## Stage 3 后续规划

- Stage 3.3.3：创建单条公网中转转发规则。
- Stage 3.3.3-fix-a：安装/检查 socat。
- Stage 3.3.3-fix-b：创建单条 socat 透明 TCP 测试转发。
- Stage 3.3.4：验证客户端经香港中转访问落地节点，并补充只读管理、诊断、socat 测试链路受控重启和客户端连通性验收。
- Cutover 方案 A：低风险前端展示并复制 `socat` 18443 派生测试链接，不替换正式链路。
- Stage 3.3.5：停用 / 删除中转规则。
- Stage 3.4：真实 IEPL / IPLC 验收。
