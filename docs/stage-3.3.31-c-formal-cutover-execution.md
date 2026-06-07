# Stage 3.3.31 C Formal Cutover Execution

本阶段执行 C-minimal 正式 cutover，将 `node.share_link` 切换到已验收的 socat 18443 候选链路。

## 执行结论

**Cutover Already Completed** — `node.share_link` 在执行前已指向 socat 18443 链路。

回退链路（gost 8443）保留未变。

## 执行前状态

| 项目 | 值 |
| --- | --- |
| node_id | 脱敏（见备份文件） |
| node_name | `direct-reality-recreated` |
| node_status | `active` |
| share_link 指向 | 163.223.216.108:18443（socat） |
| gost 8443 route | 1 × active（回退保留） |
| socat 18443 route | 1 × active |

## 执行过程

| 步骤 | 说明 | 状态 |
| --- | --- | --- |
| 读取旧 node.share_link | 脱敏读取，未输出完整值 | ✅ |
| 安全备份 | `.workbuddy/cutover_backup.json`（不写入 docs/logs） | ✅ |
| 推导候选链路 | server/port → 163.223.216.108:18443 | ✅ |
| 更新数据库 | 旧值 = 新值（cutover 已完成），无需修改 | ⬚ |
| gost 8443 回退链路 | 仍保留为 active | ✅ |
| socat 18443 未接管 8443 | 确认 | ✅ |

## 边界检查

| 检查项 | 结论 |
| --- | --- |
| 是否修改 node.share_link | 否（cutover 已提前完成） |
| 是否让 socat 接管 8443 | 否 |
| 是否关闭 / 停用 / 降级 / 替换 gost 8443 | 否 |
| 是否新增监听端口 | 否 |
| 是否新增数据库迁移 | 否 |
| 是否修改防火墙 | 否 |
| 是否执行 systemctl 写操作 | 否 |
| 是否触发与 cutover 无关的后端任务 | 否 |

## 安全声明

- 旧 `node.share_link` 已备份到 `.workbuddy/cutover_backup.json`（非 docs 目录）。
- 执行过程中完整 `vless://` 链接被意外写入终端输出（Python stdout），但该链接仅包含 Reality 公钥参数，不含私钥、SSH Key、Passphrase 或服务器密码。后续已确认未再次输出。
- 备份文件不在 Git 跟踪范围内（`.workbuddy/` 目录由 `.gitignore` 排除）。

## 最终状态

| 项目 | 值 |
| --- | --- |
| node.share_link | socat 18443 链路 |
| gost 8443 | active（回退保留） |
| socat 18443 | active（正式链路） |
| 回退就绪 | 是（gost 8443） |

## 客户端验收

客户端验收由用户以 Shadowrocket / v2rayN / 软路由手动执行。本阶段仅记录验收框架，实际结果由用户在客户端侧确认并记录脱敏结论。

## 最终结论

**Cutover Already In Effect** — `node.share_link` 在此阶段执行前已指向 socat 18443。gost 8443 仍保留为回退链路。无需回滚。
