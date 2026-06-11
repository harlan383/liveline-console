"use client";

import { FormEvent, useState } from "react";

import { apiFetch, type AuthUser } from "@/lib/api";

type LoginScreenProps = {
  initialMessage?: string;
  onLogin: (user: AuthUser) => void;
};

type LoginResult = AuthUser;

export function LoginScreen({ initialMessage, onLogin }: LoginScreenProps) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState(initialMessage ?? "");
  const [isLoading, setIsLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsLoading(true);
    setMessage("");

    try {
      const result = await apiFetch<LoginResult>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });

      if (!result.success) {
        if (result.error_code === "AUTH_RATE_LIMITED") {
          setMessage("登录尝试过多，请稍后再试。");
          return;
        }
        setMessage(result.message || "登录失败，请检查账号和密码。");
        return;
      }

      setPassword("");
      onLogin(result.data);
    } catch {
      setMessage("登录请求失败，请确认后端服务正常。");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className="login-page">
      <section className="login-card" aria-label="管理员登录">
        <div className="login-brand">
          <span className="login-kicker">LiveLine Console</span>
          <h1>管理员登录</h1>
          <p>请登录后进入服务器、节点和中转线路管理面板。</p>
        </div>

        <form className="login-form" onSubmit={handleSubmit}>
          <label>
            账号
            <input
              autoComplete="username"
              disabled={isLoading}
              name="username"
              onChange={(event) => setUsername(event.target.value)}
              placeholder="admin"
              type="text"
              value={username}
            />
          </label>
          <label>
            密码
            <input
              autoComplete="current-password"
              disabled={isLoading}
              name="password"
              onChange={(event) => setPassword(event.target.value)}
              placeholder="请输入管理员密码"
              type="password"
              value={password}
            />
          </label>

          {message ? <div className="auth-error">{message}</div> : null}

          <button className="primary" disabled={isLoading} type="submit">
            {isLoading ? "登录中..." : "登录"}
          </button>
        </form>
      </section>
    </main>
  );
}
