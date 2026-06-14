# Stage 3.3.17 Server Management UI Table

## 当前阶段结论

本阶段基于 Stage 3.3.16 已合并的 VPS 管理后端 API，将“服务器”菜单页面改造成“服务器管理”表格页。页面默认展示服务器系统记录、SSH 状态、SSH 端口、操作按钮和下级节点摘要，不再默认显示旧的读取 VPS 调试表单。

本阶段不是正式 cutover，不修改 `node.share_link`，不新增数据库迁移，不新增真实监听端口，不自动创建中转链路，不在页面加载、展开表格或打开弹窗时执行 SSH / 远程命令。

## 修改范围

修改文件：

* `frontend/components/AppShell.tsx`
* `frontend/components/ServerManagementPanel.tsx`
* `frontend/app/globals.css`
* `README.md`
* `docs/stage-3.3.17-server-management-ui-table.md`

本阶段未修改后端核心逻辑，未修改数据库模型，未新增 Alembic migration。

## 服务器管理表格

服务器页面现在默认显示“服务器管理”表格。

顶部只保留：

* 标题：服务器管理
* 按钮：添加服务器

表格列：

* 名称
* IP 地址
* 端口
* 状态
* 操作

服务器行端口显示 SSH 端口。节点下级行端口显示节点端口。

SSH 状态显示规则：

| 后端状态 | 前端显示 |
| --- | --- |
| `online` | 在线 |
| `offline` | 离线 |
| `unchecked` | 未检测 |

## 操作入口

服务器行操作包括：

* 添加节点
* 重新检测
* 编辑
* 删除

离线或未检测服务器禁止添加节点。添加节点按钮只在服务器 `last_ssh_status=online` 时可用。

## 添加服务器弹窗

添加服务器弹窗字段：

* 服务器名称
* 服务器 IP
* SSH 端口
* SSH 用户名
* 上传 SSH 私钥
* 粘贴 SSH 私钥
* 私钥密码，可选

提交后调用 `POST /api/vps`。SSH 私钥只通过现有 Redis 临时凭据机制传递，不在前端持久化，不写入文档，不写入 Git。

## 重新检测弹窗

重新检测弹窗复用 SSH 信息表单：

* SSH 端口
* SSH 用户名
* 上传 SSH 私钥
* 粘贴 SSH 私钥
* 私钥密码，可选

提交后调用 `POST /api/vps/{id}/recheck`。

## 编辑和删除

编辑服务器调用 `PATCH /api/vps/{id}`，只更新基础元数据。

删除服务器调用 `DELETE /api/vps/{id}?confirm=true`，并提供二次确认。删除操作只删除 / 隐藏系统记录，并由后端同时处理该服务器下级节点记录；不会 SSH 登录远程服务器清理 Xray 或节点配置。

## 添加节点入口

添加节点弹窗字段：

* 节点名称
* IP 地址，默认带入服务器 IP
* 端口
* 协议

由于现有 `POST /api/nodes/create-direct` 任务需要临时 SSH 凭据，本阶段在添加节点弹窗中保留上传 / 粘贴 SSH 私钥和可选私钥密码字段。提交后走现有节点创建逻辑，不新增后端能力。

节点创建任务成功后，下次刷新服务器列表时会在服务器下级表格行中展示该节点摘要。

## share_link 边界

本阶段只展示节点是否存在 `share_link`，不返回、不展示、不修改完整 `node.share_link`。服务器管理表格中只显示 `share_link：已生成 / 无`。

## 安全边界

* 是否修改后端核心逻辑：否。
* 是否修改 `node.share_link`：否。
* 是否新增数据库迁移：否。
* 是否新增监听端口：否，除非用户明确提交现有添加节点流程。
* 是否执行正式 cutover：否。
* 是否自动创建中转链路：否。
* 是否保存明文 SSH 私钥：否。
* 是否在页面加载时执行 SSH / 远程命令：否。
* 是否在展开表格时执行 SSH / 远程命令：否。
* 是否在打开弹窗时执行 SSH / 远程命令：否。

## 验收清单

* `git status` 可查看本阶段修改范围。
* `git diff --check` 通过。
* `docker compose exec -T frontend npm run build` 通过。
* `docker compose up --build -d` 通过。
* `http://localhost:3000` HTTP 200。
* `/api/health` backend / database / redis / worker 全部 ok。
* Redis `temp_credential:*` 为 0。
* pending / running tasks 为 0。
* 敏感信息扫描未发现真实 SSH Key、Passphrase、token、真实密码、`SESSION_SECRET` 真实值或完整节点链接。
