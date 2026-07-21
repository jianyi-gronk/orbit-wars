"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { ApiError, apiFetch, apiUrl, type AuthConfig, type AuthSession } from "../../src/api";
import { errorMessage, localPath, type Locale } from "../../src/i18n";

type Mode = "login" | "register" | "reset";
type ChallengeResponse = { accepted: boolean; expiresIn: number; debugCode?: string };

function safeReturnTo(value: string | undefined, locale: Locale): string {
  return value?.startsWith("/") && !value.startsWith("//") ? value : localPath(locale, "/command");
}

function AuthBrief() {
  return (
    <aside className="auth-brief" aria-hidden="true">
      <p>ORBIT ID / PERSISTENT</p>
      <div className="auth-orbit-mark">
        <span />
        <span />
        <i>◎</i>
      </div>
      <dl>
        <div>
          <dt>SESSION</dt>
          <dd>30 DAYS</dd>
        </div>
        <div>
          <dt>RECORD</dt>
          <dd>IMMUTABLE</dd>
        </div>
        <div>
          <dt>CONTROL</dt>
          <dd>AGENT</dd>
        </div>
      </dl>
    </aside>
  );
}

export function AuthPanel({
  initialMode = "login",
  locale,
  returnTo,
}: {
  initialMode?: Mode;
  locale: Locale;
  returnTo?: string;
}) {
  const zh = locale === "zh";
  const router = useRouter();
  const [mode, setMode] = useState<Mode>(initialMode);
  const [config, setConfig] = useState<AuthConfig | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [code, setCode] = useState("");
  const [codeSent, setCodeSent] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    void apiFetch<AuthConfig>("/api/auth/config")
      .then(setConfig)
      .catch(() =>
        setConfig({
          enabled: false,
          passwordEnabled: false,
          providers: { github: false, google: false },
        }),
      );
  }, []);

  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = window.setInterval(() => setCooldown((value) => Math.max(0, value - 1)), 1000);
    return () => window.clearInterval(timer);
  }, [cooldown]);

  function switchMode(next: Mode) {
    setMode(next);
    setCode("");
    setCodeSent(false);
    setConfirmation("");
    setError("");
    setNotice("");
  }

  async function requestCode() {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const endpoint =
        mode === "register" ? "/api/auth/register/request" : "/api/auth/password/request";
      const result = await apiFetch<ChallengeResponse>(endpoint, {
        body: JSON.stringify({ email, locale }),
        method: "POST",
      });
      setCodeSent(true);
      setCooldown(60);
      if (result.debugCode) setCode(result.debugCode);
      setNotice(
        result.debugCode
          ? zh
            ? "本地调试验证码已自动填入。"
            : "The local debug code has been filled in."
          : zh
            ? "验证码已发送，请检查邮箱。"
            : "Code sent. Check your inbox.",
      );
    } catch (reason) {
      setError(errorMessage(locale, reason instanceof ApiError ? reason.code : undefined));
    } finally {
      setBusy(false);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      if (mode !== "login" && password !== confirmation) {
        setError(zh ? "两次输入的密码不一致。" : "The passwords do not match.");
        return;
      }
      const endpoint =
        mode === "login"
          ? "/api/auth/login"
          : mode === "register"
            ? "/api/auth/register/complete"
            : "/api/auth/password/reset";
      const body =
        mode === "login"
          ? { email, password }
          : mode === "register"
            ? { code, displayName, email, password }
            : { code, email, password };
      await apiFetch<AuthSession>(endpoint, { body: JSON.stringify(body), method: "POST" });
      router.push(safeReturnTo(returnTo, locale));
      router.refresh();
    } catch (reason) {
      setError(errorMessage(locale, reason instanceof ApiError ? reason.code : undefined));
    } finally {
      setBusy(false);
    }
  }

  if (config === null) {
    return (
      <section className="auth-stage auth-stage--github">
        <AuthBrief />
        <div className="auth-console github-auth">
          <p className="eyebrow">IDENTITY CHANNEL / CONNECTING</p>
          <div className="auth-heading">
            <h1>{zh ? "正在建立身份通道。" : "Opening identity channel."}</h1>
            <p>{zh ? "正在读取可用的登录方式…" : "Reading available sign-in methods…"}</p>
          </div>
        </div>
      </section>
    );
  }
  const unavailable = !config.passwordEnabled;
  if (config !== null && !config.passwordEnabled) {
    const destination = safeReturnTo(returnTo, locale);
    const githubHref = apiUrl(`/api/auth/github/start?returnTo=${encodeURIComponent(destination)}`);
    return (
      <section className="auth-stage auth-stage--github">
        <AuthBrief />
        <div className="auth-console github-auth">
          <p className="eyebrow">GITHUB UPLINK / 01</p>
          <div className="auth-heading">
            <h1>{zh ? "使用 GitHub 开始。" : "Begin with GitHub."}</h1>
            <p>
              {zh
                ? "首次授权会自动建立 Orbit Wars 指挥官身份；之后使用同一个 GitHub 账号直接返回舰队。"
                : "Your first authorization creates an Orbit Wars commander. Use the same GitHub account to return to your fleet."}
            </p>
          </div>
          <div className="github-auth__facts">
            <div>
              <span>01</span>
              <strong>{zh ? "无需密码" : "NO PASSWORD"}</strong>
              <small>
                {zh ? "平台不保存你的 GitHub 密码" : "Orbit Wars never stores your GitHub password"}
              </small>
            </div>
            <div>
              <span>02</span>
              <strong>{zh ? "自动注册" : "AUTO ENLIST"}</strong>
              <small>{zh ? "首次登录自动创建账号" : "First sign-in creates the account"}</small>
            </div>
            <div>
              <span>03</span>
              <strong>{zh ? "永久航迹" : "PERSISTENT"}</strong>
              <small>
                {zh ? "舰队、策略与战绩持续保存" : "Fleet, strategy, and matches persist"}
              </small>
            </div>
          </div>
          <p className="github-auth__policy">
            {zh
              ? "首发阶段仅支持 GitHub 登录与注册。授权范围只用于识别账号和读取公开资料/已验证邮箱。"
              : "Launch access uses GitHub only. Authorization identifies your account and reads public profile data and a verified email."}
          </p>
          {config.providers.github ? (
            <a className="button button--primary github-auth__button" href={githubHref}>
              <span aria-hidden="true">◆</span>
              {zh ? "使用 GitHub 继续 →" : "Continue with GitHub →"}
            </a>
          ) : (
            <>
              <button className="button button--primary github-auth__button" disabled type="button">
                <span aria-hidden="true">◆</span>
                {zh ? "使用 GitHub 继续" : "Continue with GitHub"}
              </button>
              <div className="auth-unavailable" role="status">
                <strong>{zh ? "GITHUB 通道等待配置" : "GITHUB CHANNEL STANDBY"}</strong>
                <span>
                  {zh
                    ? "登录界面与 OAuth 回调已就绪；配置 GitHub OAuth App 与 HTTPS 回调地址后开放。"
                    : "The interface and OAuth callback are ready. Configure a GitHub OAuth App and HTTPS callback to open access."}
                </span>
              </div>
            </>
          )}
        </div>
      </section>
    );
  }
  const copy = {
    login: {
      eyebrow: "IDENTITY CHECK / 01",
      title: zh ? "返回你的舰队。" : "Return to your fleet.",
      body: zh
        ? "使用邮箱登录，继续优化策略、参与排位并查看永久保存的航迹。"
        : "Sign in with email to improve strategy, enter ranked play, and inspect your permanent record.",
      action: zh ? "进入指挥中心 →" : "Enter command →",
    },
    register: {
      eyebrow: "NEW COMMANDER / 02",
      title: zh ? "建立指挥官身份。" : "Establish a commander.",
      body: zh
        ? "无需自备 Agent。注册后可直接采用平台模板，在站内迭代代码。"
        : "No Agent required. Start from a platform template and evolve code on-site.",
      action: zh ? "注册并建立会话 →" : "Register and begin →",
    },
    reset: {
      eyebrow: "RECOVERY CHANNEL / 03",
      title: zh ? "重建访问密钥。" : "Restore access.",
      body: zh
        ? "验证邮箱并设置新密码；已有登录会话会全部失效。"
        : "Verify your email and set a new password. Existing sessions will be revoked.",
      action: zh ? "重置密码 →" : "Reset password →",
    },
  }[mode];

  return (
    <section className="auth-stage">
      <AuthBrief />
      <div className="auth-console">
        <div
          className="auth-mode-tabs"
          role="tablist"
          aria-label={zh ? "账号操作" : "Account action"}
        >
          {(["login", "register", "reset"] as const).map((value, index) => (
            <button
              aria-selected={mode === value}
              key={value}
              onClick={() => switchMode(value)}
              role="tab"
              type="button"
            >
              <span>0{index + 1}</span>
              {
                {
                  login: zh ? "登录" : "SIGN IN",
                  register: zh ? "注册" : "REGISTER",
                  reset: zh ? "找回" : "RECOVER",
                }[value]
              }
            </button>
          ))}
        </div>
        <div className="auth-heading">
          <p className="eyebrow">{copy.eyebrow}</p>
          <h1>{copy.title}</h1>
          <p>{copy.body}</p>
        </div>
        {unavailable && (
          <div className="auth-unavailable" role="status">
            <strong>{zh ? "账号通道尚未开放" : "ACCOUNT CHANNEL STANDBY"}</strong>
            <span>
              {zh
                ? "界面与后端能力已就绪；部署 HTTPS 与发信配置后启用。当前 IP 预览继续使用临时指挥官身份。"
                : "The interface and backend are ready. HTTPS and email delivery are required before activation; the IP preview keeps its temporary commander identity."}
            </span>
          </div>
        )}
        <form className="auth-form" onSubmit={submit}>
          {mode === "register" && (
            <div className="field">
              <label htmlFor="auth-display-name">{zh ? "指挥官名称" : "COMMANDER NAME"}</label>
              <input
                autoComplete="nickname"
                id="auth-display-name"
                maxLength={40}
                minLength={2}
                onChange={(event) => setDisplayName(event.target.value)}
                required
                value={displayName}
              />
            </div>
          )}
          <div className="field">
            <label htmlFor="auth-email">{zh ? "邮箱" : "EMAIL"}</label>
            <input
              autoComplete="email"
              id="auth-email"
              inputMode="email"
              onChange={(event) => setEmail(event.target.value)}
              required
              type="email"
              value={email}
            />
          </div>
          {mode !== "login" && (
            <div className="auth-code-row">
              <div className="field">
                <label htmlFor="auth-code">{zh ? "六位验证码" : "6-DIGIT CODE"}</label>
                <input
                  autoComplete="one-time-code"
                  id="auth-code"
                  inputMode="numeric"
                  maxLength={6}
                  onChange={(event) => setCode(event.target.value.replace(/\D/g, ""))}
                  pattern="[0-9]{6}"
                  required
                  value={code}
                />
              </div>
              <button
                className="button button--small"
                disabled={busy || unavailable || cooldown > 0 || !email}
                onClick={() => void requestCode()}
                type="button"
              >
                {cooldown > 0
                  ? `${cooldown}s`
                  : codeSent
                    ? zh
                      ? "重新发送"
                      : "SEND AGAIN"
                    : zh
                      ? "获取验证码"
                      : "SEND CODE"}
              </button>
            </div>
          )}
          <div className="field">
            <label htmlFor="auth-password">{zh ? "密码" : "PASSWORD"}</label>
            <input
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              id="auth-password"
              maxLength={128}
              minLength={8}
              onChange={(event) => setPassword(event.target.value)}
              required
              type="password"
              value={password}
            />
          </div>
          {mode !== "login" && (
            <div className="field">
              <label htmlFor="auth-confirmation">{zh ? "确认密码" : "CONFIRM PASSWORD"}</label>
              <input
                autoComplete="new-password"
                id="auth-confirmation"
                maxLength={128}
                minLength={8}
                onChange={(event) => setConfirmation(event.target.value)}
                required
                type="password"
                value={confirmation}
              />
            </div>
          )}
          {notice && (
            <p className="notice" role="status">
              {notice}
            </p>
          )}
          {error && (
            <p className="notice notice--error" role="alert">
              {error}
            </p>
          )}
          <button
            className="button button--primary auth-submit"
            disabled={busy || unavailable || (mode !== "login" && !codeSent)}
            type="submit"
          >
            {busy ? (zh ? "正在建立安全通道…" : "Establishing secure channel…") : copy.action}
          </button>
        </form>
      </div>
    </section>
  );
}
