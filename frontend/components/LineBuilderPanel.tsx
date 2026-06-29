"use client";

import { type ReactNode, useEffect, useMemo, useState } from "react";

import {
  apiFetch,
  type NodeData,
  type NodeListResult,
  type TaskData,
  type TaskListResult,
  type TransitResourceData,
  type TransitResourceListResult,
  type TransitRouteData,
  type TransitRouteListResult,
  type VpsServerData,
  type VpsServerListResult,
} from "@/lib/api";

type LineType = "direct" | "selfTransit" | "providerTransit";

const customerOptions = ["自己使用", "客户A", "客户B", "暂不分配", "新建客户"];
const purposeOptions = [
  "看视频 / 日常使用",
  "Facebook直播主线",
  "Facebook直播备用线",
  "TikTok直播主线",
  "TikTok直播备用线",
  "YouTube直播主线",
  "测试线路",
  "备用节点",
];

function statusLabel(status: string | null | undefined) {
  const labels: Record<string, string> = {
    active: "可用",
    online: "在线",
    worker_online: "助手在线",
    pending_worker: "等待助手",
    disabled: "停用",
    failed: "失败",
    deleted: "已删除",
  };
  return status ? labels[status] ?? status : "未返回";
}

function taskLabel(task: TaskData | null) {
  if (!task) {
    return "暂无任务";
  }
  const labels: Record<string, string> = {
    landing_node_create: "创建直连节点",
    transit_route_create: "创建中转线路",
    cleanup_landing_node: "删除落地节点",
    cleanup_landing_server: "清理落地服务器",
    cleanup_transit_route: "清理中转线路",
    cleanup_transit_resource: "清理中转服务器",
    bbr_enable_dry_run: "网络加速试运行",
    bbr_enable_real_execution: "启用网络加速",
  };
  return `${labels[task.task_type] ?? "系统任务"} / ${statusLabel(task.status)}`;
}

function endpoint(host: string | null | undefined, port: number | null | undefined) {
  if (!host) {
    return "未选择";
  }
  return port ? `${host}:${port}` : host;
}

export function LineBuilderPanel() {
  const [servers, setServers] = useState<VpsServerData[]>([]);
  const [nodes, setNodes] = useState<NodeData[]>([]);
  const [resources, setResources] = useState<TransitResourceData[]>([]);
  const [routes, setRoutes] = useState<TransitRouteData[]>([]);
  const [tasks, setTasks] = useState<TaskData[]>([]);
  const [message, setMessage] = useState("正在读取线路搭建数据。");
  const [customer, setCustomer] = useState(customerOptions[0]);
  const [purpose, setPurpose] = useState(purposeOptions[0]);
  const [lineType, setLineType] = useState<LineType>("direct");

  async function loadData() {
    const [serverResult, nodeResult, resourceResult, routeResult, taskResult] = await Promise.all([
      apiFetch<VpsServerListResult>("/api/vps"),
      apiFetch<NodeListResult>("/api/nodes"),
      apiFetch<TransitResourceListResult>("/api/transit-resources"),
      apiFetch<TransitRouteListResult>("/api/transit-routes"),
      apiFetch<TaskListResult>("/api/tasks?limit=8"),
    ]);

    if (serverResult.success) {
      setServers(serverResult.data.servers);
    }
    if (nodeResult.success) {
      setNodes(nodeResult.data.nodes);
    }
    if (resourceResult.success) {
      setResources(resourceResult.data.resources);
    }
    if (routeResult.success) {
      setRoutes(routeResult.data.routes);
    }
    if (taskResult.success) {
      setTasks(taskResult.data.tasks);
    }

    const failed = [serverResult, nodeResult, resourceResult, routeResult, taskResult].filter((result) => !result.success);
    setMessage(failed.length ? "部分数据暂时无法读取，请稍后刷新。" : "线路搭建数据已刷新。");
  }

  useEffect(() => {
    void loadData();
  }, []);

  const activeNodes = useMemo(() => nodes.filter((node) => node.status === "active"), [nodes]);
  const activeRoutes = useMemo(
    () => routes.filter((route) => route.status === "active" && !route.deleted_at),
    [routes],
  );
  const onlineLandingServers = servers.filter((server) => server.worker_online && server.status !== "deleted");
  const onlineTransitResources = resources.filter(
    (resource) => resource.worker_online && !resource.deleted_at && resource.resource_type === "server",
  );
  const providerResources = resources.filter(
    (resource) => !resource.deleted_at && resource.resource_type !== "server",
  );

  const selectedNode = activeNodes[0] ?? null;
  const selectedRoute = activeRoutes[0] ?? null;
  const selectedResource = selectedRoute
    ? resources.find((resource) => resource.id === selectedRoute.transit_resource_id)
    : onlineTransitResources[0] ?? providerResources[0] ?? null;

  const pathText =
    lineType === "direct"
      ? `用户设备 -> ${endpoint(selectedNode?.vps_ip, selectedNode?.port)}`
      : `用户设备 -> ${endpoint(selectedResource?.entry_host, selectedRoute?.listen_port ?? selectedResource?.entry_port)} -> ${endpoint(selectedRoute?.target_host ?? selectedNode?.vps_ip, selectedRoute?.target_port ?? selectedNode?.port)}`;

  return (
    <section className="customer-workspace wide">
      <div className="workspace-hero">
        <div>
          <h2>线路搭建</h2>
          <p>按客户、用途和线路类型整理搭建流程。本阶段仅做界面组织，真实创建入口会在后续阶段接入。</p>
        </div>
        <button className="secondary" type="button" onClick={() => void loadData()}>
          刷新
        </button>
      </div>

      <div className="line-entry-grid">
        <LineEntryCard
          detail={`${onlineLandingServers.length} 台落地服务器可用于搭建`}
          title="新建直连节点"
          value="直连落地，简单稳定"
        />
        <LineEntryCard
          detail={`${onlineTransitResources.length} 台自建中转服务器可用`}
          title="新建中转线路（自建中转）"
          value="自建中转，更可控"
        />
        <LineEntryCard
          detail={`${providerResources.length} 个商家入口记录`}
          title="新建中转线路（商家中转）"
          value="商家入口，快速可用"
        />
        <LineEntryCard
          detail="落地服务器 / 中转入口"
          title="添加服务器资源"
          value="下一阶段接入真实操作"
        />
      </div>

      <div className="line-builder-layout">
        <section className="panel line-builder-steps">
          <div className="status-row">
            <div>
              <h2>新线路向导</h2>
              <p className="message">先填写业务意图，再预览线路路径。</p>
            </div>
          </div>

          <div className="wizard-progress-strip" aria-label="线路搭建步骤">
            <span className="active">选择客户</span>
            <span className="active">选择用途</span>
            <span className="active">选择类型</span>
            <span>确认预览</span>
          </div>

          <WizardStep number="1" title="这条线路给谁用？">
            <SegmentedChoices options={customerOptions} value={customer} onChange={setCustomer} />
          </WizardStep>

          <WizardStep number="2" title="用途是什么？">
            <SegmentedChoices options={purposeOptions} value={purpose} onChange={setPurpose} />
          </WizardStep>

          <WizardStep number="3" title="线路类型">
            <div className="line-type-grid">
              <button
                className={lineType === "direct" ? "line-type-card selected" : "line-type-card"}
                type="button"
                onClick={() => setLineType("direct")}
              >
                <strong>直连节点</strong>
                <span>用户设备直接连接落地服务器。</span>
              </button>
              <button
                className={lineType === "selfTransit" ? "line-type-card selected" : "line-type-card"}
                type="button"
                onClick={() => setLineType("selfTransit")}
              >
                <strong>自建中转</strong>
                <span>用户设备先进入自建中转服务器，再到落地节点。</span>
              </button>
              <button
                className={lineType === "providerTransit" ? "line-type-card selected" : "line-type-card"}
                type="button"
                onClick={() => setLineType("providerTransit")}
              >
                <strong>商家中转</strong>
                <span>使用商家入口作为客户连接入口。</span>
              </button>
            </div>
          </WizardStep>
        </section>

        <section className="panel line-preview-panel">
          <div className="status-row">
            <div>
              <h2>线路预览</h2>
              <p className="message">{message}</p>
            </div>
            <span className="pill warn">只读预览</span>
          </div>

          <div className="line-preview-path" aria-label="线路路径预览">
            {pathText.split(" -> ").map((part, index) => (
              <div className="line-preview-node" key={`${part}-${index}`}>
                <span>{index === 0 ? "客户" : index === 1 && lineType !== "direct" ? "入口" : "落地"}</span>
                <strong>{part}</strong>
              </div>
            ))}
          </div>

          <div className="business-detail-grid">
            <span>客户</span>
            <strong>{customer}</strong>
            <span>用途</span>
            <strong>{purpose}</strong>
            <span>当前可用直连节点</span>
            <strong>{activeNodes.length} 条</strong>
            <span>当前可用中转线路</span>
            <strong>{activeRoutes.length} 条</strong>
            <span>最近任务</span>
            <strong>{taskLabel(tasks[0] ?? null)}</strong>
          </div>

          <div className="port-reminder">
            新增或变更客户连接端口后，请务必同步检查云服务器安全组、云防火墙、服务器防火墙是否放行。
          </div>

          <div className="line-preview-actions">
            <button disabled type="button">
              下一阶段接入真实创建
            </button>
            <button className="secondary" type="button" onClick={() => void loadData()}>
              重新读取
            </button>
          </div>
        </section>
      </div>
    </section>
  );
}

function LineEntryCard({ detail, title, value }: { detail: string; title: string; value: string }) {
  return (
    <article className="line-entry-card">
      <span>{title}</span>
      <strong>{value}</strong>
      <p>{detail}</p>
      <button disabled type="button">
        后续阶段接入
      </button>
    </article>
  );
}

function WizardStep({ children, number, title }: { children: ReactNode; number: string; title: string }) {
  return (
    <section className="wizard-step">
      <div className="wizard-step-title">
        <span>{number}</span>
        <strong>{title}</strong>
      </div>
      {children}
    </section>
  );
}

function SegmentedChoices({
  onChange,
  options,
  value,
}: {
  onChange: (nextValue: string) => void;
  options: string[];
  value: string;
}) {
  return (
    <div className="segmented-choices">
      {options.map((option) => (
        <button
          className={value === option ? "selected" : ""}
          key={option}
          type="button"
          onClick={() => onChange(option)}
        >
          {option}
        </button>
      ))}
    </div>
  );
}
