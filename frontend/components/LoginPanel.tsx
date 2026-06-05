"use client";

import { useState } from "react";
import { apiFetch } from "@/lib/api";

type LoginResult = {
  admin_id: string;
  username: string;
};

type CsrfResult = {
  csrf_token: string;
};

type LoginPanelProps = {
  onAuthChange?: (authenticated: boolean) => void;
};

export function LoginPanel({ onAuthChange }: LoginPanelProps) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [csrfToken, setCsrfToken] = useState("");
  const [message, setMessage] = useState("登录后会使用 HttpOnly Cookie Session。");

  async function login(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const result = await apiFetch<LoginResult>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });

    if (!result.success) {
      setMessage(result.message);
      return;
    }

    const csrf = await apiFetch<CsrfResult>("/api/auth/csrf");
    if (csrf.success) {
      setCsrfToken(csrf.data.csrf_token);
      setMessage(`已登录：${result.data.username}`);
      onAuthChange?.(true);
    } else {
      setMessage(csrf.message);
    }
  }

  async function logout() {
    const result = await apiFetch<Record<string, never>>("/api/auth/logout", {
      method: "POST",
      headers: csrfToken ? { "X-CSRF-Token": csrfToken } : {},
      body: JSON.stringify({}),
    });
    setCsrfToken("");
    onAuthChange?.(false);
    setMessage(result.message);
  }

  return (
    <section className="panel">
      <h2>管理员登录</h2>
      <form className="form" onSubmit={(event) => void login(event)}>
        <label>
          用户名
          <input value={username} onChange={(event) => setUsername(event.target.value)} />
        </label>
        <label>
          密码
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        <button type="submit">登录</button>
        <button className="secondary" type="button" onClick={() => void logout()}>
          退出
        </button>
        <p className="message">{message}</p>
      </form>
    </section>
  );
}
