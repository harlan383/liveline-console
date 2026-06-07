# Stage 3.3.25 C Read-Only Preflight Execution

本阶段执行 C 方案真实只读预检并记录结果。本阶段不是正式 cutover，不读取或修改 `node.share_link`，不触发后端任务，不新增数据库迁移，不新增监听端口，不修改防火墙规则，不让 `socat` 接管 8443，不关闭、停用、降级或替换 `gost` 8443。

## 当前阶段结论

- 本阶段是真实只读预检执行阶段。
- 本阶段不是正式 cutover。
- 本阶段按 Stage 3.3.24 授权执行 SSH 只读预检。
- 本阶段只执行白名单远程只读命令。
- 本阶段不读取 `node.share_link`。
- 本阶段不修改 `node.share_link`。
- 本阶段不触发后端任务。
- 本阶段不新增数据库迁移。
- 本阶段不新增监听端口。
- 本阶段不修改防火墙规则。
- 本阶段不执行 systemd start / stop / restart / disable / enable。
- 本阶段不让 `socat` 接管 8443。
- 本阶段不关闭、停用、降级或替换 `gost` 8443。

## 执行授权边界

| 授权项 | 本阶段执行情况 | 说明 |
| --- | --- | --- |
| SSH 登录服务器 | 已执行 | 仅用于只读预检 |
| 远程只读命令 | 已执行 | 仅执行白名单命令 |
| systemd 只读状态查看 | 已执行 | 仅 status / is-active / is-enabled |
| 端口监听只读查看 | 已执行 | 仅 `ss -lntp` |
| `gost` 8443 只读状态查看 | 已执行 | 未 stop / restart / disable / replace |
| `socat` 18443 只读状态查看 | 已执行 | 未修改，未接管 8443 |
| 服务器防火墙只读状态查看 | 已执行 | 仅查看，不修改 |
| 云服务器安全组 / 云防火墙查看 | 未执行 | 需要人工在云后台确认 |

## 禁止操作边界

| 禁止项 | 本阶段结果 |
| --- | --- |
| 正式 cutover | 未执行 |
| 读取 `node.share_link` | 未执行 |
| 修改 `node.share_link` | 未执行 |
| 触发后端任务 | 未执行 |
| 新增数据库迁移 | 未执行 |
| 新增监听端口 | 未执行 |
| 修改防火墙规则 | 未执行 |
| systemd start / stop / restart / disable / enable | 未执行 |
| `socat` 接管 8443 | 未执行 |
| 关闭、停用、降级或替换 `gost` 8443 | 未执行 |
| 写入真实 SSH Key / Passphrase / token / 完整节点链接 | 未执行 |

## 目标服务器信息占位

| 项目 | 值 |
| --- | --- |
| Transit host | `<TRANSIT_HOST>` |
| SSH user | `<SSH_USER>` |
| SSH port | `<SSH_PORT>` |
| `gost` route | `hk-gost-test-8443` |
| `socat` route | `hk-socat-test-18443` |
| `gost` listen port | `8443` |
| `socat` listen port | `18443` |
| Landing target | `<LANDING_HOST>:443` |

本阶段未写入真实密码、SSH Key、Passphrase、token 或完整节点链接。

## 远程只读命令白名单

本阶段实际使用的远程命令类型：

- `hostname`
- `date`
- `uptime`
- `ss -lntp`
- `ps -ef`
- `systemctl status <SERVICE_NAME> --no-pager`
- `systemctl is-active <SERVICE_NAME>`
- `systemctl is-enabled <SERVICE_NAME>`
- `ufw status`
- `iptables -S`
- `nft list ruleset`
- `nc -vz <LANDING_HOST> 443`

所有远程命令均为只读。文档不记录真实 SSH Key、Passphrase 或完整节点链接。

## 远程禁止命令清单

本阶段未执行并继续禁止：

- `systemctl start`
- `systemctl stop`
- `systemctl restart`
- `systemctl disable`
- `systemctl enable`
- 修改防火墙规则。
- 修改数据库。
- 读取或修改 `node.share_link`。
- 触发后端任务。
- 关闭、停用、降级或替换 `gost` 8443。
- 让 `socat` 接管 8443。
- 删除日志。
- 清空历史。
- 覆盖备份。
- 输出完整节点链接。
- 输出真实 SSH Key / Passphrase / token / 服务器密码。

## 执行记录表

| 检查项 | 命令类型 | 结果摘要 | 结论 |
| --- | --- | --- | --- |
| SSH 只读登录 | `hostname` | 返回目标主机标识，已脱敏 | 通过 |
| 系统时间 | `date` | 返回 `2026-06-07 18:27 CST` | 通过 |
| 运行时长 | `uptime` | 运行约 4 天 5 小时，load average 为 0.00 / 0.00 / 0.00 | 通过 |
| 监听端口 | `ss -lntp` | 22、8443、18443 监听存在 | 通过 |
| 进程状态 | `ps -ef` | `gost` 与 `socat` 进程存在 | 通过 |
| `socat` systemd | `systemctl status/is-active/is-enabled` | service loaded、enabled、active running | 通过 |
| `gost` systemd | `systemctl status` | `liveline-transit-*` service loaded、enabled、active running | 通过 |
| UFW 状态 | `ufw status` | `ufw` 命令不存在 | 信息项 |
| iptables 状态 | `iptables -S` | INPUT / FORWARD / OUTPUT 默认 ACCEPT | 通过 |
| nftables 状态 | `nft list ruleset` | 存在 mangle / nat / filter 表，策略为 accept | 通过 |
| 目标连通性 | `nc -vz <LANDING_HOST> 443` | 443 open | 通过 |

## `gost` 8443 只读检查结果

- `gost` 8443 正在监听。
- `gost` 进程存在。
- `gost` systemd service 为 `active (running)`。
- `gost` systemd service 为 `enabled`。
- `gost` 8443 仍作为正式 / 回退链路。
- 本阶段未停止、重启、禁用、降级、替换或删除 `gost` 8443。
- `systemctl status` 输出中包含近期运行日志；原始日志未写入本文档，以避免记录外部连接细节。

## `socat` 18443 只读检查结果

- `socat` 18443 正在监听。
- `socat` 进程存在。
- `socat` systemd service 为 `active (running)`。
- `socat` systemd service 为 `enabled`。
- `socat` 18443 仍作为候选链路。
- `socat` 转发目标为 `<LANDING_HOST>:443`。
- 本阶段未修改 `socat` 18443，未让 `socat` 接管 8443。

## 端口监听只读检查结果

| 端口 | 监听状态 | 进程摘要 |
| --- | --- | --- |
| 22 | LISTEN | `sshd` |
| 8443 | LISTEN | `gost` |
| 18443 | LISTEN | `socat` |

本阶段未新增监听端口，未修改任何端口监听配置。

## systemd 只读状态检查结果

| 服务 | 状态 | enabled | 备注 |
| --- | --- | --- | --- |
| `liveline-transit-*` | active running | enabled | 对应 `gost` 8443 |
| `liveline-socat-97fe351dd5e64684a37f4a00b90b4e1e.service` | active running | enabled | 对应 `socat` 18443 |

本阶段未执行 systemd start / stop / restart / disable / enable。

## 服务器防火墙只读状态检查结果

| 检查项 | 结果 |
| --- | --- |
| UFW | 命令不存在 |
| iptables | 默认 INPUT / FORWARD / OUTPUT 为 ACCEPT |
| nftables | 存在 mangle / nat / filter 表，策略为 accept |

本阶段未新增、删除或修改任何防火墙规则。

## 云服务器安全组 / 云防火墙人工确认项

本阶段未通过远程命令检查云服务器安全组或云防火墙。未来如涉及 8443 接管或监听端口变更，必须人工在云后台确认：

- 云服务器安全组 TCP 8443 是否放行。
- 云防火墙 TCP 8443 是否放行。
- 如涉及其他新增或变更监听端口，也必须确认对应 TCP 端口放行。

该人工确认项当前未完成。

## 结果脱敏规则

- 本文档不写入真实 SSH Key。
- 本文档不写入 Passphrase。
- 本文档不写入 token。
- 本文档不写入完整节点链接。
- 本文档不写入服务器密码。
- 本文档不写入 Reality privateKey。
- 主机、账号、落地目标在执行记录中使用占位符。
- 原始 `systemctl status` 日志未完整写入本文档。

## 最终预检结论

结论：`Blocked`

说明：

- 服务器侧只读预检结果为 `Ready`：SSH 只读登录成功，8443 / 18443 均在监听，`gost` / `socat` 服务均 active，服务器防火墙只读状态未发现本地阻塞，中转机到 `<LANDING_HOST>:443` 可达。
- 整体 C 方案预检仍为 `Blocked`：云服务器安全组 / 云防火墙人工确认项尚未完成，且正式 cutover、`node.share_link` 修改、`socat` 接管 8443、`gost` 8443 变更仍未授权。

## 下一步建议

- 保持 No-Go，不进入正式 cutover。
- 人工在云后台确认云服务器安全组 / 云防火墙 TCP 8443 状态。
- 如后续需要执行更多只读检查，必须另行审批范围。
- 如后续准备正式 cutover，必须单独进入 Go / No-Go 与执行 runbook 阶段。
- 继续保留 `gost` 8443 作为正式 / 回退链路。
- 继续保持 `socat` 18443 为候选链路。
- 继续禁止读取或修改 `node.share_link`，直到单独审批。

## 安全边界声明

- 本阶段执行了 SSH，只限只读预检。
- 本阶段不修改代码。
- 本阶段不修改 `.env`。
- 本阶段不写入真实 SSH Key。
- 本阶段不写入 passphrase。
- 本阶段不写入 token。
- 本阶段不写入完整节点链接。
- 本阶段不读取或修改真实数据库。
- 本阶段不读取或修改 `node.share_link`。
- 本阶段不新增数据库迁移。
- 本阶段不新增监听端口。
- 本阶段不触发后端任务。
- 本阶段不修改防火墙规则。
- 本阶段不执行 systemd start / stop / restart / disable / enable。
- 本阶段不关闭 `gost` 8443。
- 本阶段不让 `socat` 接管 `8443`。
- 本阶段不做正式 cutover。
