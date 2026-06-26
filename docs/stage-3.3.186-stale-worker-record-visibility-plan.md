# Stage 3.3.186 历史 Worker 记录显示与降噪计划

## 阶段目标

本阶段只做 README / docs 规划，不改代码、不改数据库、不远程执行。

目标：

- 记录当前正式 Worker 与历史 Worker 的区别。
- 规划 stale Worker 显示 / 降噪策略。
- 明确不物理删除旧 Worker 记录。
- 明确后续如果做代码，应优先 UI 折叠、stale 标识、last heartbeat 过期提示。
- 防止旧 `online` Worker 被误用于新节点创建。
- 保护当前正式 `28917/TCP` 直连 Reality 节点和正式 `0.1.35` landing Worker。

## 当前正式生产对象

正式直连 Reality 节点：

```text
node_name: 香港直连15m
port: 28917/TCP
status: active
Xray-core: 25.5.16
client: can access internet
```

当前正式 Worker：

```text
worker_id: redacted
server_id: redacted
hostname: ser685297596046
interface_name: ens17
role: landing
status: online
worker_version: 0.1.35-stage-3.3.182-hotfix-xray-temp-json-suffix
```

当前正式对象必须优先保护：

```text
不得误删 28917/TCP 节点。
不得隐藏当前 0.1.35 online Worker。
不得让旧 server_id / 旧 Worker 记录影响当前节点创建或升级判断。
```

## 历史 Worker 记录问题

旧 landing server 仍存在历史 Worker 记录。它们可能与当前正式 Worker 使用相同或相似的 hostname / interface，但 server 绑定已经不同，且版本较旧。

历史记录示例：

```text
server_id: redacted historical landing server

redacted | landing | deleted | 0.1.34
redacted | landing | online  | 0.1.33
redacted | landing | online  | 0.1.32
redacted | landing | online  | 0.1.32
```

风险：

```text
旧 Worker 记录可能仍显示 online。
如果 last_heartbeat_at 已明显过期，普通用户会误以为旧 server 仍有可用 Worker。
旧 Worker 可能让页面看起来有多个 landing Worker，增加选择和判断成本。
旧 Worker 不应被误用于新的 28917 相关节点创建、升级或清理流程。
```

## 显示与降噪策略

建议后续 UI / API 以派生状态区分 Worker：

### 当前 Worker

判定建议：

```text
server_id 匹配 active node 的 vps_id。
role = landing。
worker_version 满足当前 landing node create 最低版本。
last_heartbeat_at 未过期。
status = online。
```

展示建议：

```text
显示为“当前 Worker”。
显示 hostname、interface、worker_version、last_heartbeat_at。
用于创建节点、升级 Worker、状态判断。
```

### stale Worker

判定建议：

```text
status = online 但 last_heartbeat_at 已过期。
或 server_id 不再匹配当前 active production node 的 vps_id。
或版本明显旧于当前要求版本，且没有近期 heartbeat。
```

展示建议：

```text
显示为“历史 Worker / 心跳过期”。
默认折叠。
不作为创建节点默认候选。
不显示为普通可用 Worker。
```

### deleted Worker

判定建议：

```text
status = deleted。
```

展示建议：

```text
保留审计记录。
默认折叠或仅在高级调试 / 历史记录中展示。
不物理删除。
不参与 Worker targeting。
```

### historical Worker

判定建议：

```text
同 hostname / interface 下存在旧 server_id。
历史 server_id 已不再关联当前 active production node。
```

展示建议：

```text
归入“历史 Worker”分组。
显示版本和最后心跳，帮助审计。
避免与当前 Worker 混在同一主列表里。
```

## 后端 targeting 原则

后续后端创建节点时，应继续依赖 worker_targeting 的安全选择：

```text
选择 server_id 匹配目标 VPS 的 Worker。
要求 Worker 满足最低版本。
要求 Worker 有最近 heartbeat。
避免使用 stale / deleted / historical Worker。
```

建议继续保持：

```text
旧 Worker 即使 status 字段仍是 online，也不能仅凭 status 判定可用。
必须结合 last_heartbeat_at、server_id、role、版本门槛和 derived runtime status。
```

## 不建议物理删除

不建议直接物理删除 `workers` 表记录，原因：

```text
Worker 记录是生产升级、注册、清理和失败排查的审计证据。
旧记录可用于解释历史创建失败、版本升级路径和重复注册问题。
物理删除会降低可追溯性。
```

推荐顺序：

```text
1. UI 默认折叠历史 / stale / deleted Worker。
2. API 增加派生展示状态，而不修改原始 status。
3. 后续如需数据库状态标记，优先 soft marker / archived_at，而非物理删除。
4. 物理删除必须另开高风险审批阶段。
```

## 后续实现建议

后续代码阶段可以考虑：

```text
Stage 3.3.187-stale-worker-record-ui-folding
Stage 3.3.188-worker-derived-status-api-cleanup
Stage 3.3.189-worker-history-advanced-debug-panel
```

可能的 UI 分组：

```text
当前 Worker
历史 Worker
心跳过期 Worker
已删除 Worker
```

可能的派生字段：

```text
worker_display_group = current | historical | stale | deleted
worker_runtime_status = online | stale | deleted | unknown
is_current_worker = true | false
is_safe_for_node_create = true | false
```

本阶段不实现上述字段，只记录规划。

## 验证结果

```text
git diff --check: 通过
git diff --cached --check: 通过
staged diff 敏感扫描: 通过
```

本阶段只改 README / docs，不需要重建 Worker binary，不需要 frontend build，不需要 backend compileall。

## 安全边界

本阶段没有：

```text
修改代码
重建 Worker binary
修改 workers 表
修改 nodes 表
修改 tasks 表
删除 Worker 记录
删除节点
SSH / 远程执行
新建真实节点
新增真实监听端口
修改 Xray config
重启 Xray / Worker
修改防火墙 / 云安全组 / 云防火墙
输出完整 share_link
输出 UUID / privateKey / publicKey / shortId
修改 docker-compose.yml
提交 .bak 文件
执行 git reset --hard
执行 git clean -fd
```
