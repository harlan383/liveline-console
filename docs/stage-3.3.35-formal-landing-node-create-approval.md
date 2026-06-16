# Stage 3.3.35 Formal Landing Node Create Approval

## 当前阶段目标

本阶段修正落地节点创建 dry-run / 审批计划的下一阶段提示和候选端口策略。当前页面只允许生成审批计划，不允许真实创建落地节点。

当前 dry-run 下一阶段提示已统一为：

```text
Stage 3.3.35-formal-landing-node-create-approval
```

## 候选端口策略

落地节点创建计划不再默认使用 `443`。

前端默认随机选择 `10000-30000` 范围内的候选 TCP 端口，并避开常用 / 保留端口。用户也可以点击“重新随机候选端口”重新生成候选端口。

禁止选择以下端口：

```text
22, 80, 443, 8080, 8443, 18443, 3000, 3200, 8000, 8200,
5432, 6379, 15432, 16379, 10000, 27017
```

后端 dry-run 校验同样会拒绝这些常用 / 保留端口，并返回 `unsafe_port`。

## 防火墙放行要求

dry-run 页面必须明确提醒：

- 正式创建前，用户必须到云服务器安全组放行候选 TCP 端口。
- 正式创建前，用户必须到云防火墙放行候选 TCP 端口。
- 正式创建前，用户必须检查服务器本机防火墙是否放行候选 TCP 端口。
- 未完成上述确认前，不应进入正式创建。

本阶段只记录确认项，不修改任何云侧或服务器侧防火墙规则。

## 本阶段安全边界

本阶段仍然只允许生成审批计划 / dry-run。

明确不执行：

- 不安装 Xray。
- 不创建节点。
- 不新增监听端口。
- 不修改防火墙。
- 不修改云服务器安全组。
- 不修改云防火墙。
- 不修改 `node.share_link`。
- 不生成真实节点链接。
- 不执行 cutover。
- 不执行 SSH。
- 不执行远程命令。
- 不连接真实 VPS。
- 不创建任务。
- 不写入完整节点链接。
- 不写入 SSH Key。
- 不写入 Passphrase。
- 不写入 token。
- 不写入真实密码。
- 不写入 `SESSION_SECRET` 真实值。

## 修改文件

- `backend/app/services/landing_node_plan.py`
  - 将下一阶段提示改为 `Stage 3.3.35-formal-landing-node-create-approval`。
  - 扩展常用 / 保留端口禁止列表。
  - 对禁止端口返回 `unsafe_port`。
  - 对合法候选端口返回正式创建前必须放行 TCP 端口的提醒。
- `frontend/components/ServerManagementPanel.tsx`
  - 将默认候选端口从固定 `443` 改为随机 `10000-30000`。
  - 增加“重新随机候选端口”按钮。
  - 增加常用 / 保留端口前端校验。
  - 更新 dry-run 页面端口和防火墙提醒。
- `README.md`
  - 增加 Stage 3.3.35 formal landing node create approval 记录。
- `docs/stage-3.3.35-formal-landing-node-create-approval.md`
  - 记录本阶段目标、端口策略、防火墙放行要求和安全边界。

## 验收清单

- `python3 -m compileall backend/app` 通过。
- `docker compose exec -T frontend npm run build` 通过。
- `docker compose up --build -d` 通过。
- `http://localhost:3000` 返回 HTTP 200。
- `/api/health` backend / database / redis / worker 全部 ok。
- Redis `temp_credential:*` 为 0。
- pending / running tasks 为 0。
- `git diff --check` 通过。
- 敏感信息扫描通过。

## 阶段结论

Stage 3.3.35 已将落地节点 dry-run 的下一阶段提示修正为正式审批阶段，并将候选端口策略改为随机选择 `10000-30000` 的 TCP 端口，同时禁止常用 / 保留端口。当前仍为审批计划阶段，不安装 Xray，不创建节点，不新增监听端口，不修改防火墙，不修改 `node.share_link`，不生成真实节点链接，不执行 cutover。
