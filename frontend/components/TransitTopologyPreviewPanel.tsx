"use client";

import { useEffect, useMemo, useState } from "react";

import {
  apiFetch,
  type NodeData,
  type NodeListResult,
  type TransitResourceData,
  type TransitResourceListResult,
} from "@/lib/api";

const resourceTypeLabels: Record<string, string> = {
  server: "公网中转服务器",
  iepl: "IEPL 线路",
  iplc: "IPLC 线路",
  other: "其他资源",
};

const forwardingMethodLabels: Record<string, string> = {
  gost: "gost",
  nginx_stream: "nginx stream",
  socat: "socat",
  xray_dokodemo: "Xray dokodemo-door",
  manual: "人工配置",
  unknown: "未知",
};

const currentFormalLink = "socat 18443";
const currentFallbackLink = "gost 8443";
const currentShareLinkState = "已指向 socat 18443";

function displayValue(value: string | number | null | undefined) {
  return value === null || value === undefined || value === "" ? "-" : String(value);
}

function parsePort(value: string) {
  if (!value.trim()) {
    return null;
  }
  const port = Number(value);
  return Number.isInteger(port) && port >= 1 && port <= 65535 ? port : null;
}

function previewForResource(
  resource: TransitResourceData | null,
  node: NodeData | null,
  listenPort: string,
  forwardingMethod: string,
) {
  if (!resource || !node) {
    return "请选择一个启用的中转资源和一个 active 节点后生成预览。";
  }

  const parsedListenPort = parsePort(listenPort);
  const listenPortText = parsedListenPort ? String(parsedListenPort) : "端口未填写或不合法";
  const resourceType = resourceTypeLabels[resource.resource_type] ?? resource.resource_type;
  const method = forwardingMethodLabels[forwardingMethod] ?? forwardingMethod;
  const targetHost = node.vps_ip ?? "landing VPS IP 未知";
  const targetPort = node.port ?? "节点端口未知";

  const commonHeader = [
    "PREVIEW ONLY",
    "NOT USABLE",
    "这只是浏览器本地预览，不是一条可用线路。",
    "未连接远端",
    "未写入配置",
    "未保存 route",
    "未生成真实可用中转链接",
    "未修改 node.share_link",
    "未完成真实中转配置",
    "",
    `中转资源：${resource.name}`,
    `资源类型：${resourceType}`,
    `入口：${displayValue(resource.entry_host)}:${displayValue(resource.entry_port)}`,
    `入口地区：${displayValue(resource.entry_region)}`,
    `出口地区：${displayValue(resource.exit_region)}`,
    `落地节点：${node.node_name}`,
    `落地 VPS：${displayValue(node.vps_ip)}`,
    `落地节点端口：${displayValue(node.port)}`,
    `预期中转入口端口 / preview port：${listenPortText}`,
    "端口说明：preview port 只是计划值，不代表远端已经实际监听。",
    `转发方式预览：${method}`,
    "",
  ];

  if (resource.resource_type === "iepl" || resource.resource_type === "iplc") {
    return [
      ...commonHeader,
      "线路预览：client -> IEPL/IPLC entry -> provider/private line -> landing VPS/node -> platform",
      "",
      "配置责任边界预览：",
      "- 供应商侧：可能需要完成入口到出口的线路映射。",
      "- LiveLine Console：后续阶段才会考虑落地侧配置。",
      "- Stage 3.2：不验证线路，不连接供应商，不连接落地 VPS，不配置 Xray。",
      "",
      "未来链接结构预览：PREVIEW ONLY / NOT USABLE / 不生成正式 vless:// 链接。",
      "当前正式链路和回退链路不会被拓扑预览修改。",
    ].join("\n");
  }

  if (resource.resource_type === "server") {
    return [
      ...commonHeader,
      "公网服务器中转预览：client -> transit server -> landing VPS/node -> platform",
      "",
      "未来可能配置的转发关系：",
      `- listen: 0.0.0.0:${listenPortText}`,
      `- target: ${targetHost}:${targetPort}`,
      `- method: ${method}`,
      "",
      "注意：本阶段不安装 gost/nginx/socat，不配置 Xray dokodemo-door，不写防火墙或 iptables。",
      "未来链接结构预览：PREVIEW ONLY / NOT USABLE / 不生成正式 vless:// 链接。",
      "当前正式链路和回退链路不会被拓扑预览修改。",
    ].join("\n");
  }

  return [
    ...commonHeader,
    "其他资源预览：client -> transit resource -> landing VPS/node -> platform",
    "",
    "该资源类型需要后续阶段进一步确认转发责任边界和配置方式。",
    "Stage 3.2 只展示结构预览，不执行任何连接、测试或配置。",
    "当前正式链路和回退链路不会被拓扑预览修改。",
  ].join("\n");
}

export function TransitTopologyPreviewPanel() {
  const [resources, setResources] = useState<TransitResourceData[]>([]);
  const [nodes, setNodes] = useState<NodeData[]>([]);
  const [selectedResourceId, setSelectedResourceId] = useState("");
  const [selectedNodeId, setSelectedNodeId] = useState("");
  const [listenPort, setListenPort] = useState("443");
  const [forwardingMethod, setForwardingMethod] = useState("unknown");
  const [message, setMessage] = useState("中转拓扑预览只在浏览器本地生成，不保存 route。");

  async function loadPreviewData() {
    const [resourceResult, nodeResult] = await Promise.all([
      apiFetch<TransitResourceListResult>("/api/transit-resources?status=active"),
      apiFetch<NodeListResult>("/api/nodes"),
    ]);

    if (!resourceResult.success) {
      setMessage(resourceResult.message);
      return;
    }
    if (!nodeResult.success) {
      setMessage(nodeResult.message);
      return;
    }

    const activeResources = resourceResult.data.resources.filter(
      (resource) => resource.status === "active",
    );
    const activeNodes = nodeResult.data.nodes.filter((node) => node.status === "active");

    setResources(activeResources);
    setNodes(activeNodes);
    setSelectedResourceId((current) => current || activeResources[0]?.id || "");
    setSelectedNodeId((current) => current || activeNodes[0]?.id || "");
    setMessage("请选择中转资源和 active 节点查看预览。");
  }

  useEffect(() => {
    void loadPreviewData();
  }, []);

  const selectedResource = useMemo(
    () => resources.find((resource) => resource.id === selectedResourceId) ?? null,
    [resources, selectedResourceId],
  );
  const selectedNode = useMemo(
    () => nodes.find((node) => node.id === selectedNodeId) ?? null,
    [nodes, selectedNodeId],
  );
  const configPreview = previewForResource(
    selectedResource,
    selectedNode,
    listenPort,
    forwardingMethod,
  );
  const listenPortValid = parsePort(listenPort) !== null;

  return (
    <section className="panel wide">
      <div className="status-row">
        <h2>中转拓扑预览</h2>
        <button className="secondary" type="button" onClick={() => void loadPreviewData()}>
          刷新预览数据
        </button>
      </div>

      <div className="warning-box">
        <strong>PREVIEW ONLY / NOT USABLE</strong>
        <span>拓扑预览只是浏览器里的本地草图，不是一条能直接导入客户端使用的线路。</span>
        <span>本页面不会连接远端、不会写入配置、不会保存 route、不会创建真实转发。</span>
        <span>本页面不会生成真实可用中转链接，也不会修改 node.share_link。</span>
      </div>

      <div className="topology-status-strip">
        <div>
          <span>当前正式链路</span>
          <strong>{currentFormalLink}</strong>
        </div>
        <div>
          <span>当前回退链路</span>
          <strong>{currentFallbackLink}</strong>
        </div>
        <div>
          <span>node.share_link</span>
          <strong>{currentShareLinkState}</strong>
        </div>
        <p>拓扑预览不会修改以上状态，也不会读取或展示完整节点链接。</p>
      </div>

      <div className="topology-preview-layout">
        <div className="form topology-preview-form">
          <label>
            中转资源
            <select
              value={selectedResourceId}
              onChange={(event) => setSelectedResourceId(event.target.value)}
            >
              {resources.length === 0 ? <option value="">暂无 active 中转资源</option> : null}
              {resources.map((resource) => (
                <option key={resource.id} value={resource.id}>
                  {resource.name} / {resourceTypeLabels[resource.resource_type] ?? resource.resource_type}
                </option>
              ))}
            </select>
          </label>
          <label>
            active 节点
            <select value={selectedNodeId} onChange={(event) => setSelectedNodeId(event.target.value)}>
              {nodes.length === 0 ? <option value="">暂无 active 节点</option> : null}
              {nodes.map((node) => (
                <option key={node.id} value={node.id}>
                  {node.node_name} / {displayValue(node.vps_ip)}:{displayValue(node.port)}
                </option>
              ))}
            </select>
          </label>
          <label>
            预期中转入口端口 / preview port
            <input
              min={1}
              max={65535}
              type="number"
              value={listenPort}
              onChange={(event) => setListenPort(event.target.value)}
            />
            <span className="field-hint">仅用于预览，不代表远端端口已经实际监听。</span>
          </label>
          <label>
            转发方式预览
            <select
              value={forwardingMethod}
              onChange={(event) => setForwardingMethod(event.target.value)}
            >
              <option value="unknown">未知</option>
              <option value="gost">gost</option>
              <option value="nginx_stream">nginx stream</option>
              <option value="socat">socat</option>
              <option value="xray_dokodemo">Xray dokodemo-door</option>
              <option value="manual">人工配置</option>
            </select>
          </label>
          {!listenPortValid ? (
            <div className="failure-box wide-field">预期中转入口端口必须在 1-65535 之间。</div>
          ) : null}
        </div>

        <div className="topology-card">
          <h3>链路结构预览</h3>
          <div className="topology-chain">
            <div>
              <span>第 1 段：client</span>
              <strong>客户端</strong>
            </div>
            <div>
              <span>第 2 段：中转资源</span>
              <strong>{selectedResource?.name ?? "-"}</strong>
            </div>
            <div>
              <span>第 3 段：落地 VPS / 节点</span>
              <strong>
                {selectedNode
                  ? `${selectedNode.node_name} / ${displayValue(selectedNode.vps_ip)}:${displayValue(
                      selectedNode.port,
                    )}`
                  : "-"}
              </strong>
            </div>
            <div>
              <span>第 4 段：platform</span>
              <strong>目标平台 / 未指定</strong>
            </div>
          </div>

          <div className="detail-grid">
            <span>中转资源名称</span>
            <strong>{selectedResource?.name ?? "-"}</strong>
            <span>资源类型</span>
            <strong>
              {selectedResource
                ? resourceTypeLabels[selectedResource.resource_type] ?? selectedResource.resource_type
                : "-"}
            </strong>
            <span>资源入口</span>
            <strong>
              {displayValue(selectedResource?.entry_host)}:{displayValue(selectedResource?.entry_port)}
            </strong>
            <span>资源地区</span>
            <strong>
              {displayValue(selectedResource?.entry_region)} → {displayValue(selectedResource?.exit_region)}
            </strong>
            <span>active 节点</span>
            <strong>{selectedNode?.node_name ?? "-"}</strong>
            <span>落地 IP / 端口</span>
            <strong>
              {displayValue(selectedNode?.vps_ip)}:{displayValue(selectedNode?.port)}
            </strong>
            <span>预期端口 / preview port</span>
            <strong>{parsePort(listenPort) ? listenPort : "端口未填写或不合法"}</strong>
            <span>转发方式</span>
            <strong>{forwardingMethodLabels[forwardingMethod] ?? forwardingMethod}</strong>
          </div>
        </div>
      </div>

      <div className="topology-preview-output">
        <h3>配置预览</h3>
        <pre className="manual-commands">{configPreview}</pre>
      </div>

      <div className="warning-box">
        <strong>安全边界</strong>
        <div>server 公网中转不等于 IEPL / IPLC 专线。</div>
        <div>预览不包含完整 share_link、Reality privateKey、SSH Key、SSH 密码或 notes 内容。</div>
        <div>本页面不会执行 SSH、不会创建远程转发、不会新增监听端口、不会修改防火墙。</div>
        <div>本页面不会关闭 gost 8443，也不会让 socat 接管 8443。</div>
        <div>没有执行按钮、测试连接按钮、安装转发工具按钮或二维码。</div>
        <div>以后如果新增或变更监听端口，必须同步检查云服务器安全组 / 云防火墙 / 服务器防火墙是否放行对应 TCP 端口。</div>
      </div>

      <p className="message">{message}</p>
    </section>
  );
}
