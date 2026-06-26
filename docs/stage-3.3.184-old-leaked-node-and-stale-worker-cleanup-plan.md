# Stage 3.3.184 旧泄露节点与历史 Worker 清理计划

## 阶段目标

本阶段只做清理计划文档，不做真实删除、不修改数据库、不执行 SSH、不执行远程命令。

目标：

- 梳理旧泄露测试节点 `27940/TCP` 的清理策略。
- 梳理历史 Worker 记录，包括旧 `online`、`deleted`、`stale` Worker。
- 梳理失败任务与历史测试节点的处理策略。
- 明确哪些资源可以删除、哪些必须保留、哪些需要人工确认。
- 设计后续正式清理阶段的前置检查、备份、执行、回滚和验收标准。
- 防止误删当前正式可用的 `28917/TCP` 直连 Reality 节点。

## 当前生产成功状态

当前已完成：

```text
Stage 3.3.181：固定 Xray-core v25.5.16，并修复 multi-inbound preserve
Stage 3.3.182：修复 Xray 临时配置文件 .json 后缀问题
Stage 3.3.183：记录生产成功
```

当前生产摘要：

```text
公网主控 HEAD: 19369d5eba7a9bbada55f7cd2e7feb561646dd93
落地 Worker: 0.1.35-stage-3.3.182-hotfix-xray-temp-json-suffix
落地 Xray-core: Xray 25.5.16
正式新直连节点: 28917/TCP
Reality template: serverNames = dash.cloudflare.com, dest = dash.cloudflare.com:443
客户端结果: 可正常上网
```

公网主控仍有本地残留：

```text
M docker-compose.yml
*.bak 文件
```

这些属于公网部署历史端口映射 / 备份残留。本阶段不得清理、不得 reset、不得提交。

## 绝对保护对象

以下对象不得删除、不得清理、不得覆盖：

```text
正式节点端口：28917/TCP
当前正式落地 Worker：0.1.35-stage-3.3.182-hotfix-xray-temp-json-suffix
当前正式落地 Xray-core：25.5.16
当前公网主控 docker-compose.yml 本地端口映射
当前公网主控 .bak 文件
```

当前正式节点安全摘要：

```text
port = 28917
protocol = vless
security = reality
flow = xtls-rprx-vision
serverNames = ['dash.cloudflare.com']
dest = dash.cloudflare.com:443
service = liveline-xray.service active
listen = *:28917
client = can access internet
```

正式清理阶段必须先确认 `28917/TCP` 仍可用，且任何删除动作不会影响该端口对应 Node、inbound、Worker、Xray binary、Xray service 或云端放行规则。

## 待清理对象分类

### A. 旧泄露节点

候选对象：

```text
27940/TCP
```

风险原因：

```text
旧 27940 节点链接曾在聊天中暴露。
旧 27940 不是当前正式节点。
当前正式节点已切换到 28917/TCP。
```

清理建议：

- 后续正式清理阶段可以删除 `27940` 对应 Node 记录，并清理服务端旧 inbound。
- 正式执行前必须只读确认当前 managed Xray config 中是否仍存在 `27940` inbound。
- 如果当前 config 只有 `28917`，则无需远程清理 `27940` inbound，只需要清理系统记录或标记历史。
- 不得查询或记录完整 `share_link`。
- 不得输出客户端 UUID、Reality publicKey、Reality shortId 或 Reality privateKey。

### B. 历史 Worker 记录

当前可能存在多条同 `server_id` / `hostname` / `interface` 的 Worker 记录，例如：

```text
0.1.32
0.1.33
0.1.34
0.1.35
```

清理建议：

- 最新 `0.1.35` 且持续 heartbeat 的 online Worker 必须保留。
- 旧版本 `online` 但不再 heartbeat 的 Worker，可在后续阶段标记为 `stale` / `offline`。
- `deleted` 状态 Worker 记录默认保留作为审计历史，不直接物理删除。
- 不允许直接删除最新 online Worker。
- 如果要隐藏旧 Worker，优先做 UI 折叠或显示层降噪，避免破坏审计链。

### C. 失败任务记录

候选对象：

```text
Stage 3.3.181 / 3.3.182 期间失败的 landing_node_create 任务
旧 28309 / 28917 端口试建过程中的失败记录
```

清理建议：

- 失败任务保留作为生产修复审计证据。
- 不物理删除 `tasks`。
- 可以在 UI 上做归档、折叠或标记历史失败。
- 不查询 `result_data` 中可能包含完整客户端配置的字段。
- 不输出完整客户端链接。

### D. 公网主控本地残留

候选对象：

```text
M docker-compose.yml
*.bak 文件
```

清理建议：

```text
本阶段不处理。
不得执行 git reset --hard。
不得执行 git clean -fd。
不得提交 docker-compose.yml。
不得提交 .bak 文件。
```

## 后续正式清理前只读 SQL 清单

以下 SQL 仅作为后续正式清理阶段的只读检查清单。本阶段不执行。

### 1. 查询当前 active nodes

```sql
SELECT
  id,
  node_name,
  status,
  vps_id,
  xray_port,
  protocol,
  security,
  transport,
  flow,
  sni,
  dest,
  created_at,
  updated_at
FROM nodes
ORDER BY updated_at DESC
LIMIT 30;
```

要求：

```text
不得 SELECT share_link。
不得输出 UUID / publicKey / shortId / privateKey。
```

### 2. 查询目标落地服务器相关 Worker

```sql
SELECT
  id,
  role,
  status,
  server_id,
  hostname,
  interface_name,
  worker_version,
  last_heartbeat_at
FROM workers
WHERE server_id = '<landing-server-id>'
ORDER BY last_heartbeat_at DESC;
```

要求：

```text
实际执行时由操作者填入目标落地服务器 id。
不得查询 token、secret 或 worker_secret_hash 明文。
```

### 3. 查询近期 landing_node_create 任务

```sql
SELECT
  id,
  task_type,
  status,
  current_step,
  progress,
  created_at,
  updated_at,
  error_message
FROM tasks
WHERE task_type = 'landing_node_create'
ORDER BY created_at DESC
LIMIT 20;
```

要求：

```text
不查询 result_data 中的 secure_share_link。
不输出完整客户端链接。
```

## 后续正式清理前只读远程检查

以下命令仅作为后续正式清理阶段的只读检查清单。本阶段不执行。

落地 VPS：

```bash
/opt/liveline-xray/bin/xray version
systemctl is-active liveline-xray.service
ss -lntp | egrep ':27940|:28917' || true
```

安全 config 摘要：

```bash
python3 - <<'PY'
import json, os
p="/opt/liveline-xray/config/config.json"
print("config_exists =", os.path.exists(p))
with open(p) as f:
    c=json.load(f)

print("inbounds_count =", len(c.get("inbounds", [])))
for i, inbound in enumerate(c.get("inbounds", []), 1):
    ss = inbound.get("streamSettings", {})
    rs = ss.get("realitySettings", {})
    settings = inbound.get("settings", {})
    clients = settings.get("clients", [])
    print({
        "index": i,
        "tag": inbound.get("tag"),
        "listen": inbound.get("listen"),
        "port": inbound.get("port"),
        "protocol": inbound.get("protocol"),
        "network": ss.get("network"),
        "security": ss.get("security"),
        "client_count": len(clients),
        "client_flow": clients[0].get("flow") if clients else None,
        "serverNames": rs.get("serverNames"),
        "dest": rs.get("dest"),
        "privateKey_present": bool(rs.get("privateKey")),
        "shortIds_count": len(rs.get("shortIds", [])),
    })
PY
```

要求：

```text
不得输出完整 config。
不得输出 privateKey 值。
不得输出 shortId 值。
不得输出客户端 UUID。
```

## 后续正式清理阶段建议

后续可以拆成：

```text
Stage 3.3.185-old-leaked-node-safe-delete-approval
Stage 3.3.186-old-leaked-node-delete-execution
Stage 3.3.187-stale-worker-record-cleanup-plan
```

正式删除前必须满足：

```text
28917/TCP 客户端连续可用。
28917/TCP 在云安全组 / 云防火墙 / 服务器防火墙长期放行。
旧 27940 已确认不再使用。
已确认不会删除 28917 对应 Node。
已导出只读清单，但不得包含完整 share_link。
删除动作有 rollback / 审计记录。
```

## 回滚与验收原则

旧节点清理若涉及数据库软删除：

- 应优先软删除或标记历史，不做物理删除。
- 执行前记录目标对象 id、端口、状态和更新时间，但不得记录完整链接。
- 如果删除失败，应保持系统记录可见并显示失败原因。
- 如果只清理系统记录，不应停止 Xray 或修改远程 config。

旧 inbound 清理若进入远程执行阶段：

- 必须先确认 `28917/TCP` inbound 不受影响。
- 必须有配置备份与回滚方式。
- 必须通过 `xray run -test` 后才能重启服务。
- 必须重新确认 `liveline-xray.service` 为 active。
- 必须重新确认 `28917/TCP` 仍在监听。
- 不得输出完整 config、privateKey、shortId、UUID 或完整客户端链接。

历史 Worker 清理：

- 最新 online Worker 必须保留。
- stale / offline 只做状态标记或 UI 降噪。
- `deleted` 记录默认保留审计历史。
- 不做物理删除，除非后续有单独审批。

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
删除真实节点
删除服务器
删除 Worker 记录
修改 nodes
修改 workers
修改 tasks
SSH / 远程执行
新建真实节点
新增真实监听端口
修改 Xray config
重启 Xray
重启 Worker
修改防火墙 / 云安全组 / 云防火墙
输出完整 share_link
输出 UUID / privateKey / publicKey / shortId
修改 docker-compose.yml
提交 .bak 文件
执行 git reset --hard
执行 git clean -fd
```
