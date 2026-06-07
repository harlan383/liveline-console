# Stage 3.3.26 C Manual Read-Only Preflight Evidence Record

本阶段记录用户本地手动执行 SSH 只读预检后的脱敏证据结果。本阶段不是正式 cutover，不读取或修改 `node.share_link`，不触发后端任务，不新增数据库迁移，不新增监听端口，不修改防火墙规则，不执行 systemd start / stop / restart / enable / disable，不让 `socat` 接管 8443，不关闭、停用、降级或替换 `gost` 8443。

## 当前阶段结论

- 本阶段是手动 SSH 只读预检证据记录阶段。
- 本阶段不是正式 cutover。
- 本阶段只记录脱敏结果。
- 服务器侧只读预检结论为 `Ready`。
- 整体 C 方案结论仍为 `Blocked`。
- 本阶段不改变正式 cutover 的 No-Go 边界。

## Stage 3.3.25 状态修正说明

- Stage 3.3.25 曾记录 Workbuddy 环境执行真实只读预检时遇到 SSH publickey 认证失败。
- 失败原因是 Workbuddy 环境没有可用 SSH Key，并不代表目标服务器或授权私钥不可用。
- 用户随后在本地使用已授权私钥执行 SSH 只读预检。
- 用户本地 SSH 只读登录成功，且执行命令均为只读命令。
- 本阶段仅记录该本地手动只读预检的脱敏结果。
- 本阶段不改变正式 cutover 的 No-Go 结论。

## 手动只读预检执行边界

| 边界项 | 结果 |
| --- | --- |
| SSH 只读登录 | 已由用户本地手动完成 |
| 只读命令 | 已由用户本地手动执行 |
| 写操作 | 未执行 |
| 读取 `node.share_link` | 未执行 |
| 修改 `node.share_link` | 未执行 |
| 触发后端任务 | 未执行 |
| 修改防火墙 | 未执行 |
| systemd start / stop / restart / enable / disable | 未执行 |
| `socat` 接管 8443 | 未执行 |
| 关闭、停用、降级或替换 `gost` 8443 | 未执行 |
| 正式 cutover | 未执行 |

## 只读预检结果摘要表

| 检查项 | 脱敏结果摘要 | 结论 |
| --- | --- | --- |
| SSH 只读登录 | 用户本地授权私钥登录成功 | Ready |
| 基础系统状态 | 可读取 | Ready |
| 当前用户 | `root` | Ready |
| 服务器 uptime | 已确认 | Ready |
| 8443 监听 | 由 `gost` 监听 | Ready |
| 18443 监听 | 由 `socat` 监听 | Ready |
| `gost` systemd | active | Ready |
| `socat` systemd | active | Ready |
| `gost` 二进制 | `/usr/local/bin/gost` 存在 | Ready |
| `socat` 二进制 | `/usr/bin/socat` 存在 | Ready |
| 服务器侧防火墙 | iptables INPUT / FORWARD / OUTPUT policy 为 ACCEPT，未发现本地阻塞 | Ready |
| 执行命令边界 | 只读 | Ready |
| 写操作 | 未执行 | Ready |

## `gost` 8443 只读状态摘要

- 8443 正在监听。
- 监听进程为 `gost`。
- `gost` systemd 服务 active。
- `gost` 8443 当前仍作为正式 / 回退链路。
- 未执行 stop / restart / disable / replace。
- 未变更 `gost` 配置。
- 未删除或替换 `gost` route。

## `socat` 18443 只读状态摘要

- 18443 正在监听。
- 监听进程为 `socat`。
- `socat` systemd 服务 active。
- `socat` 18443 当前仍作为候选链路。
- `socat` 未接管 8443。
- 未变更 `socat` 配置。
- 未新增监听端口。

## 防火墙只读状态摘要

| 检查项 | 脱敏结果摘要 |
| --- | --- |
| 服务器侧 iptables INPUT policy | ACCEPT |
| 服务器侧 iptables FORWARD policy | ACCEPT |
| 服务器侧 iptables OUTPUT policy | ACCEPT |
| 本阶段防火墙变更 | 未执行 |
| 服务器侧本地阻塞 | 未发现 |
| 云服务器安全组 / 云防火墙 | 仍需人工确认 |

本阶段未修改任何防火墙规则，未执行 iptables / nftables 写操作，未开放或关闭任何端口。

## 云侧确认剩余阻塞项

| 阻塞项 | 当前状态 |
| --- | --- |
| 云服务器安全组 TCP 8443 是否放行 | 待人工确认 |
| 云服务器安全组 TCP 18443 是否放行 | 待人工确认 |
| 云防火墙 TCP 8443 是否放行 | 待人工确认 |
| 云防火墙 TCP 18443 是否放行 | 待人工确认 |
| 来源范围是否符合预期 | 待人工确认 |
| 是否存在云侧额外访问控制 | 待人工确认 |

凡涉及新增、变更监听端口或 8443 接管，仍必须同步检查云服务器安全组 / 云防火墙 / 服务器防火墙放行对应 TCP 端口。

## 当前最终结论

| 项目 | 结论 |
| --- | --- |
| 服务器侧只读预检 | Ready |
| 云侧安全组 / 云防火墙确认 | Pending |
| 整体 C 方案 | Blocked |
| 正式 cutover | No-Go |

服务器侧只读预检已经通过，但整体 C 方案仍被云侧安全组 / 云防火墙人工确认项，以及正式 cutover、`node.share_link` 修改、`socat` 接管 8443、`gost` 8443 变更未授权等事项阻塞。

## 下一步建议

- 进入云服务器安全组 / 云防火墙人工确认记录阶段。
- 不得直接进入正式 cutover。
- 不得修改 `node.share_link`。
- 不得让 `socat` 接管 8443。
- 不得关闭、停用、降级或替换 `gost` 8443。
- 继续保持 `gost` 8443 作为正式 / 回退链路。
- 继续保持 `socat` 18443 作为候选链路。

## 安全边界声明

- 本阶段不写入真实 SSH Key。
- 本阶段不写入 passphrase。
- 本阶段不写入 token。
- 本阶段不写入完整节点链接。
- 本阶段不写入完整原始日志。
- 本阶段不写入真实客户端 IP 明细。
- 本阶段不读取或修改 `node.share_link`。
- 本阶段不修改数据库。
- 本阶段不新增数据库迁移。
- 本阶段不新增监听端口。
- 本阶段不执行远程写命令。
- 本阶段不触发后端任务。
- 本阶段不关闭 `gost` 8443。
- 本阶段不让 `socat` 接管 8443。
- 本阶段不做正式 cutover。
