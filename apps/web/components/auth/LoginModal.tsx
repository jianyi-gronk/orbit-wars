"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";

import { apiFetch, apiUrl, type AuthConfig } from "../../src/api";
import { type Locale } from "../../src/i18n";
import { safeLoginReturnTo } from "../../src/login-modal";

const subscribeToHydration = () => () => {};

export function LoginModal({
  locale,
  onClose,
  open,
  returnTo,
}: {
  locale: Locale;
  onClose: () => void;
  open: boolean;
  returnTo?: string;
}) {
  const zh = locale === "zh";
  const mounted = useSyncExternalStore(subscribeToHydration, () => true, () => false);
  const [config, setConfig] = useState<AuthConfig | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    void apiFetch<AuthConfig>("/api/auth/config", { signal: controller.signal })
      .then(setConfig)
      .catch(() =>
        setConfig({
          enabled: false,
          passwordEnabled: false,
          providers: { github: false, google: false },
        }),
      );
    return () => controller.abort();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab" || !dialogRef.current) return;
      const focusable = Array.from(
        dialogRef.current.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
      previouslyFocused?.focus();
    };
  }, [onClose, open]);

  if (!mounted || !open) return null;

  const destination = safeLoginReturnTo(returnTo, locale);
  const githubHref = apiUrl(`/api/auth/github/start?returnTo=${encodeURIComponent(destination)}`);
  const githubReady = Boolean(config?.enabled && config.providers.github);

  return createPortal(
    <div
      className="login-modal-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        aria-describedby="orbit-login-description"
        aria-labelledby="orbit-login-title"
        aria-modal="true"
        className="login-modal"
        ref={dialogRef}
        role="dialog"
      >
        <div className="login-modal__topline" aria-hidden="true">
          <span>IDENTITY UPLINK</span>
          <span>01 / GITHUB</span>
        </div>
        <button
          aria-label={zh ? "关闭登录弹窗" : "Close sign-in dialog"}
          className="login-modal__close"
          onClick={onClose}
          ref={closeRef}
          type="button"
        >
          <span aria-hidden="true">×</span>
        </button>

        <div className="login-modal__signal" aria-hidden="true">
          <span>◎</span>
          <i />
        </div>
        <p className="eyebrow">ORBIT ID / PERSISTENT</p>
        <h2 id="orbit-login-title">{zh ? "登录 Orbit Wars" : "Sign in to Orbit Wars"}</h2>
        <p className="login-modal__description" id="orbit-login-description">
          {zh
            ? "首次使用 GitHub 会自动创建指挥官身份，舰队、策略与战绩会持续保存。"
            : "Your first GitHub sign-in creates a commander. Your fleet, strategy, and match record persist."}
        </p>

        <div className="login-modal__facts" aria-label={zh ? "登录说明" : "Sign-in details"}>
          <span>{zh ? "无需密码" : "NO PASSWORD"}</span>
          <span>{zh ? "30 天会话" : "30-DAY SESSION"}</span>
          <span>{zh ? "自动注册" : "AUTO ENLIST"}</span>
        </div>

        {config === null ? (
          <div className="login-modal__status" role="status">
            {zh ? "正在连接 GitHub…" : "Connecting to GitHub…"}
          </div>
        ) : githubReady ? (
          <a className="button button--primary login-modal__github" href={githubHref}>
            <svg aria-hidden="true" viewBox="0 0 24 24">
              <path d="M12 1.1a11.1 11.1 0 0 0-3.5 21.6c.6.1.8-.3.8-.6v-2.2c-3.4.7-4.1-1.4-4.1-1.4-.5-1.4-1.3-1.8-1.3-1.8-1.1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1.1 1.8 2.8 1.3 3.5 1 .1-.8.4-1.3.8-1.6-2.7-.3-5.5-1.3-5.5-5.9 0-1.3.5-2.4 1.2-3.2-.1-.3-.5-1.5.1-3.2 0 0 1-.3 3.3 1.2a11.5 11.5 0 0 1 6 0c2.3-1.5 3.3-1.2 3.3-1.2.7 1.7.2 2.9.1 3.2.8.8 1.2 1.9 1.2 3.2 0 4.6-2.8 5.6-5.5 5.9.4.4.8 1.1.8 2.2v3.3c0 .3.2.7.8.6A11.1 11.1 0 0 0 12 1.1Z" />
            </svg>
            {zh ? "使用 GitHub 继续" : "Continue with GitHub"}
            <span aria-hidden="true">→</span>
          </a>
        ) : (
          <div className="login-modal__status login-modal__status--error" role="status">
            {zh ? "GitHub 登录暂未开放，请稍后再试。" : "GitHub sign-in is not available yet."}
          </div>
        )}

        <p className="login-modal__policy">
          {zh
            ? "授权仅用于识别账号和读取公开资料/已验证邮箱，平台不会获得你的 GitHub 密码。"
            : "Authorization only identifies your account and reads public profile data and a verified email. Orbit Wars never receives your GitHub password."}
        </p>
      </div>
    </div>,
    document.body,
  );
}
