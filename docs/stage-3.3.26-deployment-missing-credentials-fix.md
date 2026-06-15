# Stage 3.3.26 Deployment Missing Credentials Fix

## 本阶段目标

修复公网部署时 backend 容器启动失败的问题：

```text
ModuleNotFoundError: No module named 'app.services.credentials'
```

原因是 `backend/app/services/credentials.py` 在本地存在，但被 `.gitignore` 的 `credentials*` 规则忽略，导致 main 构建产物缺少该模块。

## 修改范围

- 恢复并纳入版本控制：`backend/app/services/credentials.py`。
- 调整 `.gitignore`，继续忽略通用 `credentials*` 私密文件，但显式放行 `backend/app/services/credentials.py` 这个源码模块。
- 更新 README Stage 3.3.26 状态记录。

## credentials.py 提供内容

该模块提供现有代码引用的 Redis 临时凭据能力：

- `store_temp_credential(private_key, passphrase)`
- `pop_temp_credential(credential_id)`
- `TempCredentialExpired`
- `TempCredentialDecryptFailed`

实现方式：

- 使用 `ENCRYPTION_KEY` 派生 Fernet 加密 key。
- 将 SSH private key / passphrase 加密后写入 Redis `temp_credential:<uuid>`。
- 使用 `TEMP_CREDENTIAL_TTL_SECONDS` 设置 Redis TTL。
- Worker 读取时通过 `pop_temp_credential` 原子读取并删除 Redis key。
- 不写数据库普通字段。
- 不写日志。
- 不写任务结果。
- 不写 README 或阶段文档。

## 安全边界

- 不明文保存 SSH 私钥。
- 不把私钥、passphrase、token 写入日志、任务结果、README 或 docs。
- 未修改 `node.share_link`。
- 未新增数据库迁移。
- 未新增监听端口。
- 未执行 SSH / 远程命令。
- 未创建节点。
- 未创建中转链路。
- 未执行正式 cutover。

## 验收清单

- `python3 -m compileall backend/app` 通过。
- `docker compose exec -T frontend npm run build` 通过。
- `docker compose up --build -d` 通过。
- `docker compose exec -T backend alembic upgrade head` 通过。
- `/api/health` backend / database / redis / worker 全部 ok。
- Redis `temp_credential:*` 为 0。
- pending / running tasks 为 0。
- 敏感信息扫描通过。
