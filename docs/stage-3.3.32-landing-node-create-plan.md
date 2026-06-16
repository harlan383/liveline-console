# Stage 3.3.32 Landing Node Create Plan

## 当前阶段目标

本阶段为落地节点创建前的 dry-run 规划阶段。目标是在不执行真实创建的前提下，基于 Stage 3.3.30 的 landing readonly preflight 结果，生成“未来是否可以进入正式创建审批”的 Go / No-Go 计划。

本阶段不是正式节点创建阶段。

本阶段新增本地 dry-run 计划能力：

- 后端新增 `POST /api/vps/{server_id}/landing-node-plan`。
- 前端落地服务器下级操作从真实“添加节点”改为“创建节点计划”。
- 计划结果展示阻塞项、预检摘要、端口 / 防火墙提醒和下一阶段要求。

## 当前已知只读预检基础

Stage 3.3.30 已完成 landing readonly preflight：

| 项目 | 当前记录 |
| --- | --- |
| Worker id | `53e6535d-7b80-4121-9093-2c55b3f09953` |
| Worker version | `0.1.2-stage-3.3.30` |
| Worker role | landing |
| server id | `968519b3-9017-4b27-a9a0-d5731033f84f` |
| preflight | succeeded |
| OS | Debian 12 |
| 架构 | x86_64 |
| Worker 用户 | root |
| 当前监听 | 仅 SSH 22 |
| 80 / 443 / 8443 / 18443 | 未监听 |
| xray / x-ui / 3x-ui | 未安装 |
| nginx / caddy / socat / gost | 未安装 |
| 常见 Xray 配置路径 | 未发现 |

当前存在必须处理的预检问题：

- Worker 配置网卡为 `eth0`。
- 系统默认公网网卡为 `ens17`。
- `primary_interface_ip` 为空。
- `ss` 端口摘要存在 `port=0` 噪声。

因此本阶段会将 `interface_mismatch` 作为阻塞项提示，后续真实创建前必须先完成 Worker preflight interface normalization 或单独审批。

## 新增后端接口

新增 dry-run API：

```text
POST /api/vps/{server_id}/landing-node-plan
```

请求字段包含：

- `listen_port`
- `protocol`
- `security`
- `flow`
- `server_name`
- `dest`
- `remark`
- `allow_install_xray`
- `allow_modify_firewall`
- `allow_generate_share_link`
- `allow_overwrite_existing_config`
- `cloud_security_group_confirmed`
- `cloud_firewall_confirmed`
- `server_firewall_confirmed`
- `require_manual_cloud_firewall_confirmation`
- `require_preflight_success`

返回字段包含：

- `plan_id`
- `mode`
- `ready`
- `will_install_xray`
- `will_create_config`
- `will_open_local_firewall`
- `will_modify_cloud_security_group`
- `key_generation_strategy`
- `required_user_confirmations`
- `preflight_summary`
- `warnings`
- `blocked_reasons`
- `next_stage_required`
- `safety_boundary`

## dry-run 阻塞项

本阶段至少识别以下阻塞项：

| 阻塞项 | 含义 |
| --- | --- |
| `preflight_missing` | 缺少成功的 `landing_preflight` 结果 |
| `worker_offline` | 落地 Worker 不在线或不存在 |
| `worker_not_command_capable` | Worker 版本不支持当前预检基础 |
| `interface_mismatch` | Worker 配置网卡与默认公网网卡不一致 |
| `port_already_listening` | 计划端口已经监听 |
| `xray_existing_config_detected` | 发现已有 Xray 配置元数据 |
| `missing_cloud_firewall_confirmation` | 云安全组 / 云防火墙 / 服务器防火墙确认不完整 |
| `unsafe_port` | 端口非法、管理端口或历史问题端口 |
| `share_link_generation_not_approved` | 后续生成分享链接尚未审批 |

## 前端改动

落地服务器页面新增“创建节点计划”入口。

该入口：

- 只调用 dry-run API。
- 不调用 `POST /api/nodes/create-direct`。
- 不创建任务。
- 不提交 SSH 私钥。
- 不执行 Worker 命令。
- 不刷新或改写 `node.share_link`。

弹窗展示：

- 计划监听端口。
- VLESS / Reality / flow / serverName / dest 等未来节点参数。
- 云服务器安全组 / 云防火墙 / 服务器防火墙确认项。
- 是否允许后续安装 Xray、修改防火墙、生成分享链接、覆盖已有配置的审批占位。
- No-Go / Ready 状态。
- 预检摘要。
- 阻塞项。
- 风险提示。
- 下一阶段建议。

## 当前安全边界

本阶段明确不执行：

- 不执行 SSH。
- 不执行远程命令。
- 不连接真实 VPS。
- 不安装 Xray。
- 不写入 Xray 配置。
- 不执行 `systemctl`。
- 不新增监听端口。
- 不修改云服务器安全组。
- 不修改云防火墙。
- 不修改服务器本机防火墙。
- 不创建节点。
- 不写入 `nodes` 表。
- 不生成真实可用节点链接。
- 不输出完整节点链接。
- 不输出 UUID / Reality privateKey / shortId / token。
- 不修改 `node.share_link`。
- 不执行正式 cutover。
- 不清理旧 Worker 记录或旧 Worker 命令。

## 端口与防火墙提醒

未来任何真实落地节点创建，如果涉及新增或变更监听端口，必须先确认：

- 云服务器安全组放行对应 TCP 端口。
- 云防火墙放行对应 TCP 端口。
- 服务器本机防火墙放行对应 TCP 端口。

本阶段只记录确认状态，不修改任何云侧或服务器侧防火墙。

## 下一阶段建议

当前建议进入以下二选一后续阶段：

- `Stage 3.3.33-worker-preflight-interface-normalization`
- `Stage 3.3.35-formal-landing-node-create-approval`

在 interface mismatch 未解决或未单独审批前，不应进入真实节点创建。

## 修改文件

- `backend/app/api/routes/vps.py`
- `backend/app/schemas/landing_node_plan.py`
- `backend/app/services/landing_node_plan.py`
- `frontend/lib/api.ts`
- `frontend/components/ServerManagementPanel.tsx`
- `frontend/app/globals.css`
- `README.md`
- `docs/stage-3.3.32-landing-node-create-plan.md`

## 验收清单

- `python3 -m compileall backend/app` 通过。
- `docker compose exec -T backend python -m compileall app` 通过。
- `docker compose exec -T frontend npm run build` 通过。
- `docker compose up --build -d` 通过。
- `http://localhost:3000` 返回 HTTP 200。
- `/api/health` backend / database / redis / worker 全部 ok。
- Redis `temp_credential:*` 为 0。
- pending / running tasks 为 0。
- `git diff --check` 通过。
- 敏感信息扫描通过。

## 阶段结论

Stage 3.3.32 只增加落地节点创建 dry-run 计划能力。当前仍未进入真实节点创建，未执行 SSH / 远程命令，未新增监听端口，未安装 Xray，未修改 `node.share_link`，未生成真实节点链接，未执行正式 cutover。
