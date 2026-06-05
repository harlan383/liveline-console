"use client";

import { useState } from "react";
import { apiFetch } from "@/lib/api";

type InitResult = {
  admin_id: string;
  username: string;
};

export function InitAdminPanel() {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [initToken, setInitToken] = useState("");
  const [message, setMessage] = useState("首次启动后可初始化管理员账号。");

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const result = await apiFetch<InitResult>("/api/admin/init", {
      method: "POST",
      body: JSON.stringify({
        username,
        password,
        init_token: initToken || null,
      }),
    });

    setMessage(result.success ? `已初始化管理员：${result.data.username}` : result.message);
  }

  return (
    <section className="panel">
      <h2>管理员初始化</h2>
      <form className="form" onSubmit={(event) => void submit(event)}>
        <label>
          用户名
          <input value={username} onChange={(event) => setUsername(event.target.value)} />
        </label>
        <label>
          密码
          <input
            minLength={12}
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        <label>
          初始化 Token
          <input
            type="password"
            value={initToken}
            onChange={(event) => setInitToken(event.target.value)}
          />
        </label>
        <button type="submit">初始化</button>
        <p className="message">{message}</p>
      </form>
    </section>
  );
}
