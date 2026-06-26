# Stage 3.3.182 Xray 临时配置文件 JSON 后缀 hotfix

## 阶段目标

修复 Stage 3.3.181 部署后创建新直连 Reality 节点失败的问题。

落地 Worker 已升级到：

```text
0.1.34-stage-3.3.181-xray-v25516-multi-inbound
```

真实创建新直连节点时，Worker 写入临时配置并调用：

```text
xray run -test -config <tempPath>
```

但临时文件路径为：

```text
/opt/liveline-xray/config/.config.json.<unixnano>.tmp
```

Xray-core v25.5.16 根据文件最终后缀判断配置格式，`.tmp` 后缀无法识别为 JSON，导致配置测试失败。

## 修复内容

- 将 LiveLine-managed Xray 临时配置文件命名从 `.config.json.<unixnano>.tmp` 改为 `.config.<unixnano>.json`。
- `xray run -test -config <tempPath>` 使用的临时配置路径现在最终以 `.json` 结尾。
- 新增 Worker 单测，确认临时配置路径以 `.json` 结尾。
- 新增 Worker 单测，确认 Xray 配置测试命令中的 `-config` 参数路径以 `.json` 结尾。
- 保留 Stage 3.3.181 的 Xray v25.5.16 pin、sha256 校验、managed state backup allowlist、multi-inbound append、duplicate port 拒绝和 `spx=%2F` 导出行为。

## Worker 版本

新 Worker 版本：

```text
0.1.35-stage-3.3.182-hotfix-xray-temp-json-suffix
```

Bundled Linux amd64 Worker binary：

```text
backend/worker-binaries/liveline-worker-linux-amd64
```

sha256：

```text
76ce855d0b63d03fdf53261d23030beb9e0f990d04d72689b098927f09986e83
```

## 同步更新

- 后端 landing node create Worker 最低版本门槛升级到 `0.1.35-stage-3.3.182-hotfix-xray-temp-json-suffix`。
- Worker 安装/升级页面展示版本同步到 `0.1.35-stage-3.3.182-hotfix-xray-temp-json-suffix`。
- Transit Worker 升级验收 checksum 同步到新 binary sha256。

## 验证结果

- `git diff --check`：通过。
- `git diff --cached --check`：通过。
- `python3 -m compileall backend/app backend/tests`：通过。
- `cd worker && go test ./...`：通过。
- `cd worker && go build ./...`：通过。
- `GOOS=linux GOARCH=amd64 CGO_ENABLED=0 go build -o ../backend/worker-binaries/liveline-worker-linux-amd64 ./cmd/liveline-worker`：通过。
- `shasum -a 256 backend/worker-binaries/liveline-worker-linux-amd64`：`76ce855d0b63d03fdf53261d23030beb9e0f990d04d72689b098927f09986e83`。
- `cd frontend && node node_modules/next/dist/bin/next build`：通过，使用 bundled Node。

## 安全边界

本阶段只修改代码、测试、文档和 bundled Worker binary。

本阶段没有：

- 新建真实节点。
- 新增真实监听端口。
- SSH 或远程执行。
- 真实升级 Xray。
- 修改防火墙、云安全组或云防火墙。
- 输出完整 `share_link`。
- 修改 `docker-compose.yml`。
- 提交 `.bak` 文件。
