# Stage 3.3.14 UI zh-CN Collapsible Tips

## 当前阶段结论

本阶段将本地控制台的主要用户界面中文化，并把大面积安全提示改为默认折叠展示。本阶段不是正式 cutover，不修改 `node.share_link`，不新增监听端口，不新增数据库迁移，不执行 SSH 或远程命令。

## 中文化范围

- 左侧导航栏改为中文：总览、服务器、节点、中转链路、任务中心、诊断工具、设置。
- 顶部状态栏、总览卡片、任务状态、节点状态、线路状态、按钮和空状态文案改为中文。
- 任务记录页将任务状态、当前步骤、进度、错误码、任务结果摘要等展示标签改为中文。
- 节点页将节点状态、备份文件类型、任务状态等展示文案改为中文。
- VPS 读取页将任务状态展示改为中文。
- 中转链路页将线路详情、诊断结果、只读预检结果、端口提示和本地规划提示尽量改为中文。

以下技术名词保留原样：`node.share_link`、`socat`、`gost`、`Xray`、`Reality`、`VLESS`、`API`、`SSH`、`TCP`、端口号、接口名、文件名和数据库字段名。

## 折叠安全提示范围

以下大面积提示区块改为默认折叠，用户可点击“查看说明”展开：

- 当前链路保护说明。
- 中转资源安全边界。
- 单条转发安全门槛。
- Formal cutover 风险提示。
- 本地规划边界。
- 只读预检安全边界。
- 诊断安全边界。
- 单条线路端口提醒。
- 候选链接安全提示。
- 诊断排查提示。
- 任务记录安全提示。

折叠后页面主功能区域优先展示，安全内容仍保留在页面中，未删除。

## 保留的安全内容

- 不要误改 `node.share_link`。
- 当前正式入口已经指向 `socat 18443`。
- `gost 8443` 继续保留为回退链路。
- 不要让 `socat` 接管 `8443`。
- 不要误删或覆盖 `socat 18443`。
- 中转资源只是服务器资源记录，不等于已经创建可用线路。
- 真实转发必须进入单条转发流程，并经过明确确认。
- 以后新增或变更监听端口时，必须同步检查云服务器安全组 / 云防火墙 / 服务器防火墙。
- 当前阶段不是正式 cutover。
- 危险操作必须二次确认。

## 危险操作显示规则

危险操作附近仍保留短提示或确认，不完全隐藏：

- 删除节点。
- 删除远端 failed 备份候选文件。
- 创建或变更监听端口。
- 复制候选正式链接。
- 诊断或重启相关操作。
- 任何未来修改正式链路、修改 `node.share_link`、执行 cutover、关闭回退链路、覆盖 `socat` / `gost` 配置的操作。

## 修改范围

- `frontend/components/AppShell.tsx`
- `frontend/components/NodesPanel.tsx`
- `frontend/components/ReadVpsPanel.tsx`
- `frontend/components/TaskHistoryPanel.tsx`
- `frontend/components/TransitRoutesPanel.tsx`
- `frontend/components/RouteSafetyGuardrails.tsx`
- `frontend/app/globals.css`
- `README.md`
- `docs/stage-3.3.14-ui-zh-cn-collapsible-tips.md`

`RouteSafetyGuardrails.tsx` 是现有链路保护提示的共享组件，本阶段只调整其展示方式为默认折叠，不改变业务逻辑。

## 风险边界

- 未修改后端核心逻辑。
- 未修改 API 兼容性。
- 未修改 `node.share_link`。
- 未新增数据库迁移。
- 未新增监听端口。
- 未执行 SSH。
- 未执行远程命令。
- 未触发后端任务。
- 未执行正式 cutover。
- 未关闭、停用、降级或替换 `gost 8443`。
- 未让 `socat` 接管 `8443`。
- 未覆盖 `socat 18443`。

## 验收清单

- 左侧导航和主要页面用户可见文案已改为中文。
- 状态标签显示为正常、警告、异常、未检测、等待中、执行中、失败、成功等中文。
- 当前链路保护、中转资源安全边界、cutover 风险提示等大块提示默认折叠。
- 展开后仍能看到完整安全边界说明。
- 删除、端口变更、候选链接复制等风险操作附近仍有短提示或确认。
- 页面不展示完整节点链接。
- 页面不展示 SSH Key、密码、token、`SESSION_SECRET`。
- `node.share_link` 未修改。
- 未新增监听端口。
- 未执行远程命令。
- 未执行正式 cutover。
