"use client";

import { useEffect, useState } from "react";
import { apiFetch, type HealthData } from "@/lib/api";

const labels: Record<keyof HealthData, string> = {
  backend: "Backend",
  database: "PostgreSQL",
  redis: "Redis",
  worker: "RQ Worker",
};

export function SystemStatus() {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [message, setMessage] = useState("正在读取系统状态");

  async function loadHealth() {
    try {
      const result = await apiFetch<HealthData>("/api/health");
      if (result.success) {
        setHealth(result.data);
        setMessage(result.message);
      } else {
        setMessage(result.message);
      }
    } catch {
      setMessage("无法连接后端");
    }
  }

  useEffect(() => {
    void loadHealth();
  }, []);

  return (
    <section className="panel">
      <h2>系统状态</h2>
      <div className="status-list">
        {health ? (
          (Object.keys(labels) as Array<keyof HealthData>).map((key) => {
            const item = health[key];
            const ok = item.status === "ok";
            return (
              <div className="status-row" key={key}>
                <div>
                  <strong>{labels[key]}</strong>
                  <p className="message">{item.detail ?? item.status}</p>
                </div>
                <span className={`pill ${ok ? "ok" : "bad"}`}>{item.status}</span>
              </div>
            );
          })
        ) : (
          <p className="message">{message}</p>
        )}
      </div>
      <div style={{ marginTop: 14 }}>
        <button className="secondary" onClick={() => void loadHealth()}>
          刷新状态
        </button>
      </div>
    </section>
  );
}
