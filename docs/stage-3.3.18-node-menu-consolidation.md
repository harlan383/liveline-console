# Stage 3.3.18 Node Menu Consolidation

## 当前阶段结论

本阶段将“节点”从左侧一级菜单中合并到“服务器管理”页面。新的产品结构以服务器作为一级管理对象，节点作为服务器的下级资源展示和操作。

本阶段不是正式 cutover，不修改 `node.share_link`，不新增数据库迁移，不新增真实监听端口，不执行 SSH / 远程命令，不创建真实节点，不创建中转链路。

## 为什么移除左侧“节点”菜单

Stage 3.3.17 已经将“服务器”页面改造成服务器管理表格，并在每台服务器下显示下级节点摘要。继续保留左侧一级“节点”菜单会让用户在“全局节点列表”和“服务器下级节点”之间困惑。

因此 Stage 3.3.18 移除左侧“节点”菜单入口，但不删除节点底层能力。

## 节点功能迁移位置

节点能力统一迁移到：

* 服务器管理
* 服务器下级节点行
* 节点操作按钮：查看、复制、二维码
* 节点详情弹窗

服务器下级节点行默认只展示：

* 节点名称
* IP 地址
* 节点端口
* 协议
* 状态
* `share_link` 是否已生成
* 操作按钮

## 保留的节点能力

本阶段保留并迁移以下能力：

* 节点详情查看
* 完整 `share_link` 复制
* 完整 `share_link` 显示 / 隐藏
* 本地二维码显示 / 隐藏
* 节点 Reality 参数展示

二维码沿用旧 `NodesPanel.tsx` 中已有的 `react-qr-code` 前端本地生成方式。二维码等同完整节点链接，只在用户点击“二维码”后显示。

## 节点详情迁移

节点详情通过现有 `GET /api/nodes/{id}` 按需读取，不在服务器列表默认加载时批量读取完整 `share_link`。

详情弹窗展示：

* 节点名称
* VPS IP / 服务器 IP
* 协议
* 端口
* 状态
* `share_link` 状态
* Reality serverName
* Reality publicKey
* shortId
* flow
* 分享链接区域

如果后端没有返回某个字段，前端显示 `-`，不写死假数据。

## share_link 边界

本阶段不修改 `node.share_link`。

允许：

* 默认展示 `share_link：已生成 / 未生成`
* 用户点击“查看”后在详情弹窗中查看脱敏链接
* 用户点击“显示完整链接”后展示完整链接
* 用户点击“复制”后复制完整链接
* 用户点击“二维码”后显示本地二维码

不允许：

* 修改 `node.share_link`
* 重写 `node.share_link`
* 自动切换 `node.share_link`
* 自动执行 cutover
* 默认批量暴露完整 `share_link`

## NodesPanel 文件处理

旧 `frontend/components/NodesPanel.tsx` 文件暂时保留，避免一次性删除造成大范围风险。左侧导航和 `AppShell` 页面切换逻辑已经不再引用旧 `NodesPanel`。

旧节点页中的核心详情、复制链接和二维码思路已迁移到 `ServerManagementPanel.tsx`。

## API 使用结论

本阶段复核后确认现有 API 足够支持迁移：

* `GET /api/vps` 用于服务器表格和节点摘要。
* `GET /api/nodes/{id}` 用于用户点击后按需读取节点详情和完整 `share_link`。

未发现必须新增后端 API 的缺口。

## 安全提示

服务器管理页新增默认折叠提示“查看节点合并说明”，说明：

* 节点已合并到服务器管理页。
* 节点属于某一台服务器。
* 左侧不再提供独立节点菜单。
* `share_link` 只在用户明确点击查看或复制时展示。
* 本阶段不修改 `node.share_link`。
* 本阶段不创建真实节点。
* 本阶段不新增监听端口。
* 本阶段不执行正式 cutover。
* 后续新增或变更节点监听端口时，必须同步检查云服务器安全组 / 云防火墙 / 服务器防火墙是否放行对应 TCP 端口。

## 安全边界

* 是否修改后端核心逻辑：否。
* 是否新增数据库迁移：否。
* 是否修改 `node.share_link`：否。
* 是否新增监听端口：否。
* 是否创建真实节点：否。
* 是否创建中转链路：否。
* 是否执行 SSH / 远程命令：否。
* 是否执行正式 cutover：否。
* 是否删除 `nodes` 表、模型或 API：否。
* 是否删除 `POST /api/nodes/create-direct`：否。
* 是否默认批量暴露完整 `share_link`：否。

## 验收清单

* 左侧不再显示“节点”一级菜单。
* 服务器管理页仍可打开。
* 服务器下级节点行显示节点摘要。
* 节点下级行默认只显示 `share_link` 状态。
* 点击“查看”后按需读取节点详情。
* 点击“复制”后按需读取并复制完整链接。
* 点击“二维码”后按需读取并显示本地二维码。
* `git diff --check` 通过。
* `docker compose exec -T frontend npm run build` 通过。
* `docker compose up --build -d` 通过。
* `http://localhost:3000` HTTP 200。
* `/api/health` backend / database / redis / worker 全部 ok。
* Redis `temp_credential:*` 为 0。
* pending / running tasks 为 0。
* 敏感信息扫描未发现真实 SSH Key、Passphrase、token、真实密码、`SESSION_SECRET` 真实值或完整节点链接样例。
