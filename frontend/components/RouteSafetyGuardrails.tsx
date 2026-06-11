"use client";

type RouteSafetyGuardrailsProps = {
  context?: "global" | "resources" | "routes" | "topology";
};

const contextNotes: Record<NonNullable<RouteSafetyGuardrailsProps["context"]>, string[]> = {
  global: [
    "不要误改 node.share_link；当前正式入口已经指向 socat 18443。",
    "不要关闭 gost 8443；它继续保留为回退链路。",
    "不要让 socat 接管 8443，也不要误删或覆盖 socat 18443。",
  ],
  resources: [
    "中转资源只是服务器资源记录，不等于已经创建了可用线路。",
    "真正转发必须进入单条转发流程，并经过明确确认。",
    "本页面的资源编辑不会创建转发，也不会把资源变成可导入客户端的线路。",
  ],
  routes: [
    "新增或变更监听端口前，必须先确认云服务器安全组、云防火墙和服务器防火墙已放行对应 TCP 端口。",
    "不要使用 8443 作为新的 socat 转发端口；8443 当前保留给 gost 回退链路。",
    "修改正式链路前必须另开正式切换审批阶段。",
  ],
  topology: [
    "拓扑预览只做本地展示，不连接远端、不新增监听端口、不修改 node.share_link。",
    "拓扑预览不会创建真实线路，也不会关闭 gost 8443。",
    "预期端口只是 preview port，不代表远端已经实际监听。",
  ],
};

const contextTitle: Record<NonNullable<RouteSafetyGuardrailsProps["context"]>, string> = {
  global: "当前链路保护",
  resources: "中转资源安全边界",
  routes: "单条转发安全边界",
  topology: "拓扑预览链路保护",
};

export function RouteSafetyGuardrails({ context = "global" }: RouteSafetyGuardrailsProps) {
  return (
    <section className={`route-safety-guardrail ${context}`} aria-label={contextTitle[context]}>
      <div className="route-safety-heading">
        <span>Route Guardrails</span>
        <strong>{contextTitle[context]}</strong>
      </div>
      <div className="route-safety-grid">
        <div>
          <span>当前正式链路</span>
          <strong>socat 18443</strong>
        </div>
        <div>
          <span>当前回退链路</span>
          <strong>gost 8443</strong>
        </div>
        <div>
          <span>node.share_link</span>
          <strong>已指向 socat 18443</strong>
        </div>
      </div>
      <ul className="route-safety-list">
        {contextNotes[context].map((note) => (
          <li key={note}>{note}</li>
        ))}
        <li>以后新增或变更监听端口时，必须同步检查云服务器安全组 / 云防火墙 / 服务器防火墙。</li>
      </ul>
    </section>
  );
}
