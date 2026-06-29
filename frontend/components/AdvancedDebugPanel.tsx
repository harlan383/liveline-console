"use client";

import { ServerManagementPanel } from "@/components/ServerManagementPanel";
import { SystemStatus } from "@/components/SystemStatus";
import { TransitRoutesPanel } from "@/components/TransitRoutesPanel";
import { TransitServersPanelWithWorkerFolding } from "@/components/TransitServersPanelWithWorkerFolding";
import { TransitTopologyPreviewPanel } from "@/components/TransitTopologyPreviewPanel";

export function AdvancedDebugPanel() {
  return (
    <section className="advanced-debug-workspace wide">
      <div className="workspace-hero debug">
        <div>
          <h2>高级调试</h2>
          <p>这里保留原有技术视图、任务细节、服务器助手状态和底层线路操作。普通线路搭建请优先使用左侧主菜单。</p>
        </div>
      </div>

      <SystemStatus />
      <ServerManagementPanel />
      <TransitServersPanelWithWorkerFolding />
      <TransitRoutesPanel />
      <TransitTopologyPreviewPanel />
    </section>
  );
}
