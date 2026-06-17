# Stage 3.3.40 Share-link Redaction and Export Confirmation

## 阶段目标

本阶段对节点 `share_link` 做前后端安全加固。目标是让默认列表、详情、任务展示不直接暴露完整节点链接，只有用户明确点击导出 / 复制并完成二次确认后，才由后端在单次响应中返回完整链接。

本阶段不轮换现有节点、不重建节点、不修改 `node.share_link` 内容，也不改变当前可用服务。

## 执行边界

- 不执行 SSH / 远程命令。
- 不连接公网主控 VPS。
- 不连接落地 VPS。
- 不部署公网主控。
- 不重装 Worker。
- 不安装、重启或停止 Xray。
- 不创建、删除或轮换节点。
- 不新增监听端口。
- 不修改云安全组 / 云防火墙 / 服务器防火墙。
- 不修改现有 `node.share_link` 内容。
- 不生成新的真实节点链接。
- 不执行 cutover。

## 后端默认脱敏策略

默认节点列表和节点详情 API 不再返回完整 `share_link`。默认响应只返回：

- `has_share_link`
- `share_link_present`
- `share_link_length`
- `masked_share_link`

`masked_share_link` 只保留协议前缀和 `[redacted]` 标记，不包含完整连接材料。

默认节点详情还会对连接材料做打码摘要：

- 不返回完整节点 UUID。
- 不返回完整 Reality public key。
- 不返回完整 shortId。
- 不返回 Reality privateKey。

任务结果和任务日志 API 在返回浏览器前会做递归脱敏，避免历史任务结果中的 `share_link`、token、密码、私钥、session 等敏感字段直接展示。

## 显式导出接口策略

新增显式导出接口：

```text
POST /api/nodes/{node_id}/share-link/export
```

请求必须包含：

```json
{
  "confirm_export": true,
  "reason": "client_import"
}
```

接口规则：

- 未确认导出时返回 400。
- 节点不存在时返回 404。
- 节点没有 `share_link` 时返回 409。
- 成功时仅在本次响应中返回完整链接。
- 后端不把完整链接写入日志、阶段文档、README 或任务结果。
- 返回 warning，提醒 `share_link` 是敏感信息，不应粘贴到聊天、日志、PR 或文档。

## 前端二次确认策略

前端默认只显示：

- 是否已生成链接。
- 链接长度。
- 完整链接已隐藏。
- 脱敏链接摘要。

以下动作必须由用户点击并二次确认：

- 导出并复制节点链接。
- 临时显示完整链接。
- 显示二维码。
- 生成 socat 候选客户端链接。

确认文案会提示：节点链接属于敏感信息，只应用于导入客户端，不应粘贴到聊天、PR、日志或文档中。

## 不展示 / 不记录完整链接原则

- README 不记录完整链接。
- 阶段文档不记录完整链接。
- 终端日志不输出完整链接。
- 浏览器默认不展示完整链接。
- 任务记录默认不展示完整链接。
- QR code 等同完整链接，只能在用户二次确认后临时显示。
- 查询数据库或排障时优先使用 `has_share_link`、`share_link_length` 或打码字段。

## 创建成功结果展示

节点创建成功后，页面只展示：

- 节点创建成功。
- `share_link` 已写入。
- 完整链接默认隐藏。
- 需要点击导出并复制链接。

创建结果不会默认把完整链接渲染到页面上。

## 安全边界

本阶段没有修改现有 `node.share_link` 值，没有生成新的真实节点链接，没有修改节点配置，没有改变 Xray 服务状态，没有新增监听端口，也没有执行任何远程操作。

敏感信息不得写入：

- README。
- docs。
- PR 描述。
- 终端日志。
- 浏览器 console。
- 聊天记录。
- 任务日志。

## 验收清单

- `git diff --check` 通过。
- `python3 -m compileall backend/app` 通过。
- `PYTHONPATH=backend python3 -m unittest discover -s backend/tests` 通过。
- `docker compose exec -T frontend npm run build` 通过。
- 默认节点列表 API 不返回完整 `share_link`。
- 默认节点详情 API 不返回完整 `share_link`。
- 导出接口缺少确认时拒绝。
- 导出接口只有确认后才返回完整链接。
- 前端默认隐藏完整链接。
- 前端导出 / 复制 / 二维码动作有二次确认。
- 敏感信息扫描未发现完整节点链接、Reality privateKey、完整 Worker setup token、真实密码、`SESSION_SECRET` 或数据库密码。

## 后续建议

- `Stage 3.3.41-node-key-rotation-runbook`
- `Stage 3.3.43-transit-integration-planning`
