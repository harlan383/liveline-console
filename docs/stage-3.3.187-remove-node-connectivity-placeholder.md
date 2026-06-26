# Stage 3.3.187 删除直连节点连通性占位显示

## 阶段目标

删除落地服务器页面直连节点卡片中的“连通性：待检测”占位展示，避免普通用户误以为系统已经做了真实客户端连通性检测，或误以为当前节点存在问题。

本阶段只做前端展示清理和 README / docs 记录，不修改后端创建节点逻辑、不修改 Worker、不修改 Xray、不修改数据库字段、不修改 `share_link`。

## 背景

当前正式直连 Reality 节点已经成功：

```text
node_name: 香港直连15m
port: 28917/TCP
status: active
Xray-core: 25.5.16
Worker: 0.1.35-stage-3.3.182-hotfix-xray-temp-json-suffix
service_status: active
client: v2rayN 已验证可正常上网
```

但前端落地服务器页面仍显示：

```text
连通性：待检测
```

该字段目前并不是 LiveLine 自动执行的客户端可用性检测结果，继续显示会造成误导。

## UI 变更

删除直连节点主卡片和节点摘要弹窗中的连通性占位展示。

保留：

```text
已启用
服务状态：服务已启动
客户端配置：已生成
查看摘要
复制客户端链接
临时二维码
删除节点
```

不再展示：

```text
连通性：待检测
```

底层 API 中的 `connectivity_status` 等字段暂时保留，不做数据库迁移，也不强行删除后端字段。

## 产品判断

当前 `28917/TCP` 节点已经通过人工客户端验证可正常上网。

“连通性：待检测”不是自动检测结果，因此不应作为主列表状态展示。

后续如果要重新引入连通性概念，应单独设计：

```text
人工标记已验证
客户端回传检测
受控只读诊断
明确检测时间与检测来源
```

不能继续用默认占位值模拟真实检测。

## 验证结果

```text
git diff --check: 通过
git diff --cached --check: 通过
frontend build: 通过
staged diff 敏感扫描: 通过
```

本阶段未修改后端，不需要 backend compileall。

## 安全边界

本阶段没有：

```text
删除真实节点
新增真实节点
新增监听端口
修改 Xray config
重启 Xray
重启 Worker
SSH / 远程执行
修改防火墙 / 云安全组 / 云防火墙
修改 nodes / workers / tasks 数据
输出完整 share_link
输出 UUID / privateKey / publicKey / shortId
修改 docker-compose.yml
提交 .bak 文件
执行 git reset --hard
执行 git clean -fd
```
