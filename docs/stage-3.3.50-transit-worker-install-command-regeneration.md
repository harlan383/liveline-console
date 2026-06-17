# Stage 3.3.50 Transit Worker Install Command Regeneration

## 阶段目标

本阶段为中转服务器列表增加“重新生成 Worker 安装命令”能力，解决 `pending_worker` 中转服务器关闭安装命令弹窗后无法找回完整 token / install command、又不能删除重建的问题。

本阶段只新增本地控制台 API 和 UI 入口，不执行远程安装，不执行 Worker 命令，不创建中转链路。

## 问题背景

当前添加中转服务器流程会：

1. 保存中转服务器资源记录。
2. 将资源状态设为 `pending_worker`。
3. 生成 role = `transit` 的一次性 Worker token。
4. 将 token 绑定到 `worker_tokens.server_id = transit_resources.id`。
5. 前端只在本次响应中展示完整安装命令。

完整命令关闭后不会再次展示，这是正确的安全设计。但如果用户关闭弹窗且未复制命令，就会留下一个 `pending_worker` 中转服务器记录，无法继续安装，也不能为了找回 token 而删除重建。

## 新增能力

- `pending_worker` 且 Worker 未在线的中转服务器行显示“重新生成安装命令”按钮。
- 点击按钮后，后端为已有 `transit_resources.id` 重新生成 role = `transit` 的一次性 Worker token。
- 前端展示新的安装命令区域，并支持复制。
- 安装命令仍只在本次响应中显示。
- 前端明确提示不要将命令写入聊天、Git、README、PR、日志或截图。

## 后端策略

新增 API：

```text
POST /api/transit-resources/{resource_id}/worker-bootstrap/regenerate
```

请求要求：

- 必须是已登录 admin session。
- 必须携带 CSRF token。
- 请求体可包含 `expires_in_minutes`，默认 60 分钟。

资源校验：

- 中转资源必须存在。
- `deleted_at` 必须为空。
- `resource_type` 必须为 `server`。
- 当前状态必须为 `pending_worker`。
- 该资源不能已有 online transit Worker。

成功行为：

- 将同一 `server_id` + role = `transit` + status = `active` 的旧 token 标记为 `revoked`。
- 调用现有绑定 token 创建流程生成新 token。
- 返回新的 `masked_token`、`expires_at` 和本次响应可见的安装命令。
- 写入 audit action：`regenerate_transit_resource_worker_bootstrap`。

失败行为：

- 已有 online Worker 时返回清晰错误。
- 非 `pending_worker` 状态返回清晰错误。
- `PUBLIC_CONSOLE_URL` / `WORKER_PUBLIC_BASE_URL` 缺失、非法或 localhost 时，沿用现有公网主控地址错误响应。

## 前端策略

中转服务器表格中：

- 仅 `connection_mode = worker`、`pending_worker`、且 Worker 未在线的资源显示“重新生成安装命令”。
- 点击按钮调用新 API。
- 成功后弹出安装命令区域。
- 复用现有复制逻辑。
- 失败时展示后端 `error_code` 和 message。

前端不会：

- 显示旧 token。
- 返回或展示 `token_hash`。
- 返回或展示 `worker_secret`。
- 返回或展示 `worker_secret_hash`。
- 在页面加载、展开行或打开普通弹窗时自动生成 token。

## 旧 Token 失效策略

同一中转服务器下旧的 active transit Worker token 会被标记为 `revoked`。

这样可以避免用户误用多个仍有效的一次性安装命令，同时不删除历史 token 记录，也不影响已注册 Worker 的 `used` token 历史。

## 安全边界

本阶段不执行：

- SSH。
- Worker 命令。
- Worker 安装。
- 中转链路创建。
- `socat` / `gost` 安装。
- 新监听端口创建。
- 云安全组、云防火墙或服务器本机防火墙修改。
- Xray 修改。
- `nodes.share_link` 修改。
- 完整客户端链接导出。
- cutover。

敏感信息不得写入 README、docs、PR、日志、终端输出或截图：

- 真实 token。
- 完整 Worker 安装命令。
- SSH 私钥。
- 数据库密码。
- 完整 `vless://`。
- 完整 `nodes.share_link`。

## 验收清单

- `git diff --check` 通过。
- `python3 -X pycache_prefix=/private/tmp/liveline-pycache -m compileall backend/app` 通过。
- `docker compose exec -T frontend npm run build` 通过。
- 未新增数据库 migration。
- 敏感信息扫描未发现真实 token、完整 Worker 安装命令、SSH 私钥、数据库密码、完整 `vless://` 或完整 `nodes.share_link`。

## 当前阶段结论

本阶段补齐了 `pending_worker` 中转服务器的安装命令恢复路径。用户仍需手动在目标 VPS 执行新命令；系统不会自动安装 Worker，也不会远程创建中转链路。
