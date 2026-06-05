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
    "未连接远端",
    "未写入配置",
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
    `预期中转监听端口：${listenPortText}`,
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
    ].join("\n");
  }

  return [
    ...commonHeader,
    "其他资源预览：client -> transit resource -> landing VPS/node -> platform",
    "",
    "该资源类型需要后续阶段进一步确认转发责任边界和配置方式。",
    "Stage 3.2 只展示结构预览，不执行任何连接、测试或配置。",
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
        <span>本阶段不会连接远端、不会写入配置、不会生成真实可用中转链接。</span>
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
            预期中转入口端口
            <input
              min={1}
              max={65535}
              type="number"
              value={listenPort}
              onChange={(event) => setListenPort(event.target.value)}
            />
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
          <h3>拓扑</h3>
          <div className="topology-chain">
            <div>
              <span>client</span>
              <strong>客户端</strong>
            </div>
            <div>
              <span>transit resource</span>
              <strong>{selectedResource?.name ?? "-"}</strong>
            </div>
            <div>
              <span>landing VPS / node</span>
              <strong>
                {selectedNode
                  ? `${selectedNode.node_name} / ${displayValue(selectedNode.vps_ip)}:${displayValue(
                      selectedNode.port,
                    )}`
                  : "-"}
              </strong>
            </div>
            <div>
              <span>platform</span>
              <strong>目标平台</strong>
            </div>
          </div>

          <div className="detail-grid">
            <span>资源类型</span>
            <strong>
              {selectedResource
                ? resourceTypeLabels[selectedResource.resource_type] ?? selectedResource.resource_type
                : "-"}
            </strong>
            <span>入口</span>
            <strong>
              {displayValue(selectedResource?.entry_host)}:{displayValue(selectedResource?.entry_port)}
            </strong>
            <span>地区</span>
            <strong>
              {displayValue(selectedResource?.entry_region)} → {displayValue(selectedResource?.exit_region)}
            </strong>
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
        <div>server 公网中转不等于 IEPL / IPLC 专线。</div>
        <div>预览不包含完整 share_link、Reality privateKey、SSH Key、SSH 密码或 notes 内容。</div>
        <div>没有执行按钮、测试连接按钮、安装转发工具按钮或二维码。</div>
      </div>

      <p className="message">{message}</p>
    </section>
  );
}
