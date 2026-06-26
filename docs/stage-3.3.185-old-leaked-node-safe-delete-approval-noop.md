# Stage 3.3.185 旧泄露节点安全删除 no-op 审批记录

## 阶段目标

记录旧泄露测试节点 `27940/TCP` 的只读核查与安全删除审批结论。

本阶段只做 README / docs 记录，不修改代码、不重建 Worker binary、不修改数据库、不执行 SSH、不执行远程命令、不删除节点、不重启 Xray。

## 当前正式生产对象

正式节点：

```text
node_name: 香港直连15m
node_id: redacted
vps_id: redacted
xray_port: 28917
status: active
protocol: vless
security: reality
transport: tcp
flow: xtls-rprx-vision
sni: dash.cloudflare.com
dest: dash.cloudflare.com:443
client: can access internet
```

正式 Worker：

```text
worker_id: redacted
server_id: redacted
hostname: ser685297596046
interface_name: ens17
role: landing
status: online
worker_version: 0.1.35-stage-3.3.182-hotfix-xray-temp-json-suffix
last_heartbeat_at: 2026-06-26 13:34:01.552713+00
```

服务端只读检查结果：

```text
liveline-xray.service: active
ss -lntp: only *:28917 LISTEN
27940: not listening
config_exists = True
inbounds_count = 1
inbound tag = liveline-reality-28917
port = 28917
protocol = vless
network = tcp
security = reality
client_flow = xtls-rprx-vision
serverNames = ['dash.cloudflare.com']
dest = dash.cloudflare.com:443
```

## 旧泄露节点状态

旧泄露测试节点：

```text
node_name: 香港落地15m
node_id: redacted
vps_id: redacted
xray_port: 27940
status: deleted
protocol: vless
security: reality
transport: tcp
flow: xtls-rprx-vision
sni: dash.cloudflare.com
dest: dash.cloudflare.com:443
```

只读结论：

```text
数据库中 27940 节点已经是 deleted。
服务端 Xray config 中已经不存在 27940 inbound。
服务端没有 27940 listener。
当前只有 28917/TCP 正式节点在监听。
```

因此：

```text
不需要远程删除 27940 inbound。
不需要重启 Xray。
不需要修改 Xray config。
不需要删除数据库记录。
```

## 历史 Worker 记录

旧 landing server 上存在历史 Worker 记录，例如：

```text
0.1.34 deleted
0.1.33 online but historical
0.1.32 online but historical
0.1.32 online but historical
```

本阶段不修改这些记录。

后续如需处理，应单独进入 stale Worker 降噪 / 归档阶段：

```text
优先 UI 折叠或派生状态标记。
优先保留审计历史。
不做物理删除。
不允许删除当前正式 online Worker。
```

## no-op 审批结论

本阶段审批结果为 no-op：

```text
不删除真实节点。
不修改远程 Xray config。
不重启 Xray。
不删除 Worker 记录。
不修改 nodes / workers / tasks。
不执行 SSH。
不修改防火墙。
```

原因：

```text
旧 27940 数据库记录已经 deleted。
旧 27940 服务端 inbound 已不存在。
旧 27940 没有监听。
当前正式 28917 节点 active 且可正常上网。
继续执行远程清理没有收益，反而存在误伤 28917 的风险。
```

## 后续建议

旧 27940：

```text
保持 deleted 历史记录。
不要恢复为 active。
不要作为正式长期节点继续使用。
不需要远程 cleanup。
```

正式 28917：

```text
继续作为当前正式直连 Reality 节点。
保持 28917/TCP 在云安全组、云防火墙和服务器防火墙长期放行。
后续任何清理阶段都必须先确认不会影响 28917 inbound、liveline-xray.service 或当前 Worker。
```

历史 Worker：

```text
后续单独规划 stale Worker 记录降噪 / 归档。
不在本阶段处理。
```

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
