# Stage 3.3.183 Production success record

## 阶段目标

记录 Stage 3.3.181 与 Stage 3.3.182 部署后的生产成功结果。

本阶段只做 README / docs 记录，不修改代码、不重建 Worker binary、不执行远程命令、不新增监听端口、不修改防火墙、不输出完整客户端配置。

## 已合并阶段

Stage 3.3.181：

```text
PR: #255
Merge commit: aeb1781fe411431cb12003629faafe1e3588b688
Worker: 0.1.34-stage-3.3.181-xray-v25516-multi-inbound
sha256: f045c96bae690dbfbf07fa03cfa6288b882de1ee38340a69e8696467c75cf379
```

Stage 3.3.182：

```text
PR: #256
Merge commit: 84f8bf91a24e305638e295c21fe609282363577c
Worker: 0.1.35-stage-3.3.182-hotfix-xray-temp-json-suffix
sha256: 76ce855d0b63d03fdf53261d23030beb9e0f990d04d72689b098927f09986e83
```

## 公网主控部署验证

公网主控当前已部署到：

```text
main HEAD: 84f8bf91a24e305638e295c21fe609282363577c
```

只读验收结果：

```text
backend health: success true
frontend: HTTP/1.1 200 OK
postgres / redis: healthy
worker binary sha256: 76ce855d0b63d03fdf53261d23030beb9e0f990d04d72689b098927f09986e83
```

## 落地 Worker 验收

落地 Worker 已升级成功：

```text
hostname: ser685297596046
interface: ens17
role: landing
worker_version: 0.1.35-stage-3.3.182-hotfix-xray-temp-json-suffix
sha256: 76ce855d0b63d03fdf53261d23030beb9e0f990d04d72689b098927f09986e83
status: online
```

## 新直连 Reality 节点验收

Stage 3.3.182 部署后，新直连 Reality 节点创建成功：

```text
port: 28917/TCP
protocol: vless
security: reality
flow: xtls-rprx-vision
transport: tcp
serverNames: dash.cloudflare.com
dest: dash.cloudflare.com:443
Xray-core: 25.5.16
liveline-xray.service: active
listen: *:28917
client result: v2rayN can access internet successfully
```

服务端只读验证摘要：

```text
/opt/liveline-xray/bin/xray version:
Xray 25.5.16 (go1.24.3 linux/amd64)

systemctl is-active liveline-xray.service:
active

ss -lntp:
*:28917 LISTEN users:(("xray",pid=<redacted>,fd=3))
```

Xray config 安全摘要：

```text
config_exists = True
inbounds_count = 1
tag = liveline-reality-28917
listen = 0.0.0.0
port = 28917
protocol = vless
network = tcp
security = reality
client_count = 1
client_flow = xtls-rprx-vision
serverNames = ['dash.cloudflare.com']
dest = dash.cloudflare.com:443
privateKey_present = True
shortIds_count = 1
```

本文档不记录完整 `share_link`、客户端 UUID、Reality publicKey、Reality shortId 或 Reality privateKey。

## 重大修复结论

1. 服务端 Xray-core 25.1.1 会导致当前 Reality / Vision 组合出现：

   ```text
   REALITY: processed invalid connection
   ```

2. 手动升级服务端 Xray-core 到 v25.5.16 后，旧 27940 测试节点恢复可上网。

3. 因此 LiveLine-managed Xray-core 默认固定到：

   ```text
   v25.5.16
   ```

4. Stage 3.3.181 修复了：

   ```text
   Xray-core v25.5.16 pin
   旧版本升级
   multi-inbound preserve
   spx=%2F 导出
   xray.backup.YYYYMMDD-HHMMSS managed state artifact allowlist
   ```

5. Stage 3.3.182 修复了：

   ```text
   Xray v25.5.16 通过文件后缀识别 config 格式。
   临时文件 .config.json.<nano>.tmp 会失败。
   临时配置文件必须最终以 .json 结尾，例如 .config.<nano>.json。
   ```

6. Stage 3.3.182 部署后，新节点 28917/TCP 创建成功并可正常上网。

## 旧节点风险记录

旧测试节点：

```text
27940/TCP
```

状态说明：

```text
旧 27940 节点链接曾在聊天中暴露。
旧 27940 不建议作为正式长期节点使用。
新 28917 节点为未泄露正式节点。
28917/TCP 需要长期保留云安全组、云防火墙、服务器防火墙放行。
```

## 验证结果

```text
git diff --check: 通过
git diff --cached --check: 通过
```

本阶段只改 README / docs，不需要重建 Worker binary，不需要 frontend build。

## 安全边界

本阶段没有：

```text
新建真实节点
新增真实监听端口
删除真实节点
删除服务器
SSH / 远程执行
真实升级 Worker
真实升级 Xray
修改防火墙 / 云安全组 / 云防火墙
输出完整 share_link
输出客户端 UUID / privateKey / publicKey / shortId
修改 docker-compose.yml
提交 .bak 文件
```
