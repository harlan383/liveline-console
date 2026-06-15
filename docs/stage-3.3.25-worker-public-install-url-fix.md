# Stage 3.3.25 Worker Public Install URL Fix

## 本阶段目标

修复 Worker 安装命令使用 `localhost` 的问题。远程 VPS 执行安装命令时，`localhost` 会指向远程 VPS 自身，因此安装脚本和 Worker binary 必须使用远程 VPS 可访问的主控公网地址。

## 修改范围

- 后端新增 `PUBLIC_CONSOLE_URL` / `WORKER_PUBLIC_BASE_URL` 配置读取。
- `POST /api/worker-tokens` 只使用配置的公网主控地址生成安装命令。
- `GET /worker_setup_script/{token}` 也使用同一个公网主控地址生成 Worker 注册地址和 binary 下载地址。
- 落地服务器 / 中转服务器添加弹窗增加公网主控地址提示。
- `.env.example` 和 `docker-compose.yml` 增加公网主控地址配置项。
- README 增加 Stage 3.3.25 记录。

## 安装命令规则

安装命令格式：

```bash
curl -s <PUBLIC_CONSOLE_URL>/worker_setup_script/<token> | bash -s eth0 landing
```

中转服务器使用 `transit` role：

```bash
curl -s <PUBLIC_CONSOLE_URL>/worker_setup_script/<token> | bash -s eth0 transit
```

如果 `PUBLIC_CONSOLE_URL` / `WORKER_PUBLIC_BASE_URL` 未配置，后端拒绝生成安装命令，并返回：

```text
主控公网地址未配置，远程 VPS 无法通过 localhost 访问安装脚本。
```

如果配置为 `localhost`、`127.0.0.1`、`0.0.0.0` 或 `::1`，后端同样拒绝生成命令。

## 前端提示

落地服务器和中转服务器 Worker 接入弹窗都提示：

- 生成命令必须先配置 `PUBLIC_CONSOLE_URL`。
- 主控公网地址未配置时，远程 VPS 无法通过 `localhost` 访问安装脚本。
- 生成命令后，请在 VPS 上先确认能访问主控地址。
- 明文 token 只出现在一次性安装命令中，不得写入 README、阶段文档、终端日志或 Git。

## 环境变量

`.env.example` 只保留占位符：

```env
PUBLIC_CONSOLE_URL=
WORKER_PUBLIC_BASE_URL=
```

`PUBLIC_CONSOLE_URL` 应配置为远程 VPS 可访问的主控后端公网地址，例如 `https://console.example.com`。如 Worker bootstrap 需要使用不同地址，可设置 `WORKER_PUBLIC_BASE_URL` 覆盖。

## 安全边界

- 未修改 `node.share_link`。
- 未新增监听端口。
- 未执行 SSH / 远程命令。
- 未连接真实 VPS。
- 未安装 Worker 到真实 VPS。
- 未创建节点。
- 未创建中转链路。
- 未修改后端核心部署逻辑。
- 未新增数据库迁移。
- 未执行正式 cutover。
- 未写入真实密码、真实 token、SSH Key、Passphrase、SESSION_SECRET 或完整节点链接。

## 验收清单

- `git diff --check` 通过。
- `python3 -m compileall backend/app` 通过。
- `docker compose exec -T frontend npm run build` 通过。
- `docker compose up --build -d` 通过。
- `http://localhost:3000` 返回 HTTP 200。
- `/api/health` backend / database / redis / worker 全部 ok。
- Redis `temp_credential:*` 为 0。
- pending / running tasks 为 0。
- 安装命令生成逻辑不再回退到 `localhost`。
- 敏感信息扫描通过。
