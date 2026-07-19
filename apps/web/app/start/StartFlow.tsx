"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

import { ApiError, apiFetch, type Fleet } from "../../src/api";
import { humanPlayEnabled } from "../../src/features";
import { errorMessage, localPath, type Locale } from "../../src/i18n";

type Control = "human" | "agent";
type Tendency = "balanced" | "assault" | "expansion" | "defense";
type StrategyTemplate = "platform-basic" | "kaggle-structured-v11";

const tendencies: Tendency[] = ["balanced", "assault", "expansion", "defense"];
const strategyTemplates: StrategyTemplate[] = ["platform-basic", "kaggle-structured-v11"];

export function StartFlow({ locale = "zh" }: { locale?: Locale }) {
  const zh = locale === "zh";
  const [step, setStep] = useState(0);
  const [control, setControl] = useState<Control>(humanPlayEnabled ? "human" : "agent");
  const [fleetName, setFleetName] = useState("");
  const [tendency, setTendency] = useState<Tendency>("balanced");
  const [strategyTemplate, setStrategyTemplate] = useState<StrategyTemplate>("platform-basic");
  const [declaration, setDeclaration] = useState(
    zh ? "让每一次出击都有证据。" : "Leave evidence in every orbit.",
  );
  const [styleDescription, setStyleDescription] = useState("");
  const [fleet, setFleet] = useState<Fleet | null>(null);
  const [fleetReady, setFleetReady] = useState(false);
  const [checking, setChecking] = useState(true);
  const [authenticated, setAuthenticated] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    void apiFetch<{ authenticated: boolean }>("/api/v1/session", { signal: controller.signal })
      .then(async (session) => {
        setAuthenticated(session.authenticated);
        if (!session.authenticated) return;
        try {
          const owned = await apiFetch<Fleet>("/api/v1/me/fleet", { signal: controller.signal });
          setFleet(owned);
          setFleetReady(owned.currentStrategyStatus === "ready");
          setStep(2);
        } catch (reason) {
          if (reason instanceof Error && reason.name === "AbortError") return;
          if (!(reason instanceof ApiError && reason.code === "fleet.not_found")) {
            setError(errorMessage(locale, reason instanceof ApiError ? reason.code : undefined));
          }
        }
      })
      .catch(() => setAuthenticated(false))
      .finally(() => setChecking(false));
    return () => controller.abort();
  }, [locale]);

  async function establish(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const created = await apiFetch<Fleet>("/api/v1/fleets", {
        body: JSON.stringify({
          commanderCode: `${fleetName.trim().slice(0, 30)}-01`,
          declaration,
          name: fleetName,
          strategyTemplate,
          strategyTendency: tendency,
          styleDescription,
        }),
        method: "POST",
      });
      setFleet(created);
      setFleetReady(true);
      setStep(1);
    } catch (reason) {
      const code = reason instanceof ApiError ? reason.code : undefined;
      if (code === "fleet.already_exists") {
        try {
          const owned = await apiFetch<Fleet>("/api/v1/me/fleet");
          setFleet(owned);
          setFleetReady(owned.currentStrategyStatus === "ready");
          setStep(2);
          return;
        } catch {
          // Fall through to the localized API error when the existing fleet cannot be loaded.
        }
      }
      setError(errorMessage(locale, code));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="panel">
      {checking && <p>{zh ? "正在检查你的舰队状态…" : "Checking your fleet status…"}</p>}
      {!checking && !authenticated && (
        <section className="start-gate">
          <p className="eyebrow">SIGN IN / STEP 00</p>
          <h2>{zh ? "先登录，再建立舰队" : "Sign in, then establish your fleet"}</h2>
          <p className="page-lede">
            {zh
              ? "登录后会自动回到这里；你的舰队与战绩会永久保存。"
              : "You will return here automatically. Your fleet and match record will persist."}
          </p>
          <Link
            className="button button--primary"
            href={`/auth/login?returnTo=${encodeURIComponent(localPath(locale, "/start"))}`}
          >
            {zh ? "登录并开始 →" : "Sign in and start →"}
          </Link>
        </section>
      )}
      {!checking && authenticated && (
        <>
          <div
            className="progress-rail"
            aria-label={zh ? `创建进度 ${step + 1}/3` : `Creation progress ${step + 1}/3`}
          >
            {[0, 1, 2].map((index) => (
              <span data-active={index <= step} key={index} />
            ))}
          </div>
          {step === 0 && (
            <form onSubmit={establish}>
              <p className="eyebrow">01 / FLEET IDENTITY</p>
              <h2>{zh ? "建立你的舰队" : "Establish your fleet"}</h2>
              <p className="form-intro">
                {zh
                  ? "选择一套可运行的初始策略，之后随时可以让 Agent 继续改进。"
                  : "Choose a runnable starter strategy, then let an Agent improve it whenever you want."}
              </p>
              <div className="field">
                <label htmlFor="fleet-name">{zh ? "舰队名" : "Fleet name"}</label>
                <input
                  id="fleet-name"
                  maxLength={80}
                  onChange={(event) => setFleetName(event.target.value)}
                  placeholder={zh ? "例如：极光航迹" : "For example: Aurora Trace"}
                  required
                  value={fleetName}
                />
              </div>
              <div className="field">
                <label htmlFor="silhouette">{zh ? "原创外观描述" : "Original appearance"}</label>
                <textarea
                  id="silhouette"
                  onChange={(event) => setStyleDescription(event.target.value)}
                  placeholder={
                    zh
                      ? "例如：深蓝环形船体、三枚琥珀导航翼、银色引擎光带"
                      : "For example: dark blue ring hull, three amber fins, silver engine trail"
                  }
                  required
                  rows={3}
                  value={styleDescription}
                />
              </div>
              <fieldset className="template-picker">
                <legend>02 / {zh ? "初始策略模板" : "STARTER STRATEGY TEMPLATE"}</legend>
                <div className="template-grid">
                  {strategyTemplates.map((value) => {
                    const copy = {
                      "platform-basic": zh
                        ? ["平台基础", "Signal Cadet", "轻量、透明，适合从零开始迭代。"]
                        : [
                            "PLATFORM",
                            "Signal Cadet",
                            "Lightweight and transparent; ideal for starting from zero.",
                          ],
                      "kaggle-structured-v11": zh
                        ? ["KAGGLE", "Structured v11", "公开的到达时刻预测与任务分层基线。"]
                        : [
                            "KAGGLE",
                            "Structured v11",
                            "A public arrival-time and mission-layer baseline.",
                          ],
                    }[value];
                    return (
                      <button
                        aria-pressed={strategyTemplate === value}
                        className="template-option"
                        data-source={value === "platform-basic" ? "platform" : "kaggle"}
                        key={value}
                        onClick={() => setStrategyTemplate(value)}
                        type="button"
                      >
                        <span className="mode-tag">{copy[0]}</span>
                        <strong>{copy[1]}</strong>
                        <small>{copy[2]}</small>
                      </button>
                    );
                  })}
                </div>
                <a
                  className="template-source"
                  href="https://www.kaggle.com/code/pilkwang/orbit-wars-structured-baseline"
                  rel="noreferrer"
                  target="_blank"
                >
                  {zh ? "查看 Kaggle 原始模板 ↗" : "View the Kaggle source ↗"}
                </a>
              </fieldset>
              <fieldset className="style-picker">
                <legend>03 / {zh ? "初始战斗风格" : "STARTER BATTLE STYLE"}</legend>
                <div className="style-grid">
                  {tendencies.map((value) => {
                    const copy = {
                      balanced: zh
                        ? ["均衡", "扩张、进攻与防守保持平衡。"]
                        : ["Balanced", "Balance expansion, attack, and defense."],
                      assault: zh
                        ? ["突击", "更早集结兵力，主动争夺敌方轨道。"]
                        : ["Assault", "Mass forces early and pressure enemy orbits."],
                      expansion: zh
                        ? ["扩张", "优先占领中立星球，扩大生产优势。"]
                        : ["Expansion", "Claim neutral planets and grow production."],
                      defense: zh
                        ? ["防守", "稳住核心星球，等待更干净的机会。"]
                        : ["Defense", "Protect core planets and wait for clean openings."],
                    }[value];
                    return (
                      <button
                        aria-pressed={tendency === value}
                        className="style-option"
                        key={value}
                        onClick={() => setTendency(value)}
                        type="button"
                      >
                        <strong>{copy[0]}</strong>
                        <small>{copy[1]}</small>
                      </button>
                    );
                  })}
                </div>
              </fieldset>
              <details className="advanced-profile">
                <summary>{zh ? "可选：舰队宣言" : "Optional: fleet declaration"}</summary>
                <div className="field">
                  <label htmlFor="declaration">{zh ? "公开宣言" : "Public declaration"}</label>
                  <textarea
                    id="declaration"
                    onChange={(event) => setDeclaration(event.target.value)}
                    rows={2}
                    value={declaration}
                  />
                </div>
              </details>
              {error && (
                <p className="notice notice--error" role="alert">
                  {error}
                </p>
              )}
              <button className="button button--primary" disabled={busy} type="submit">
                {busy
                  ? zh
                    ? "正在建立…"
                    : "Establishing…"
                  : zh
                    ? "创建舰队并继续 →"
                    : "Create fleet and continue →"}
              </button>
            </form>
          )}
          {step === 1 && fleet && (
            <section>
              <p className="eyebrow">02 / FIRST COMMAND</p>
              <h2>
                {fleet.name} {zh ? "已就位" : "is online"}
              </h2>
              <p className="page-lede">
                {humanPlayEnabled
                  ? zh
                    ? "数据库已创建舰队并绑定可验证的基础策略。选择首场由谁控制；这个标签不会拆分排名。"
                    : "Your fleet is persisted with a verified starter strategy. Choose who controls the first match; this label never splits the ranking."
                  : zh
                    ? "数据库已创建舰队并绑定可验证的基础策略。首场比赛将由 Agent 自主执行。"
                    : "Your fleet is persisted with a verified starter strategy. The first match will run autonomously under Agent control."}
              </p>
              {humanPlayEnabled ? (
                <div className="choice-grid">
                  {(["human", "agent"] as const).map((choice) => (
                    <button
                      aria-pressed={control === choice}
                      className="choice-card"
                      key={choice}
                      onClick={() => setControl(choice)}
                      type="button"
                    >
                      <span className="mode-tag" data-tone={choice}>
                        {choice.toUpperCase()}
                      </span>
                      <strong>
                        {choice === "human"
                          ? zh
                            ? "亲自指挥"
                            : "Command it"
                          : zh
                            ? "交给 Agent"
                            : "Delegate to Agent"}
                      </strong>
                      <small>
                        {choice === "human"
                          ? zh
                            ? "在服务器时钟内亲自发令。"
                            : "Issue commands on the server clock."
                          : zh
                            ? "使用当前 ready 版本执行。"
                            : "Run the current ready version."}
                      </small>
                    </button>
                  ))}
                </div>
              ) : (
                <div className="agent-lock" role="status">
                  <span aria-hidden="true" className="agent-lock__mark">
                    ◎
                  </span>
                  <div className="agent-lock__copy">
                    <strong>{zh ? "Agent 自主执行" : "Agent autonomous"}</strong>
                    <small>
                      {zh
                        ? "首场比赛使用当前 ready 策略。"
                        : "The first match uses the ready strategy."}
                    </small>
                  </div>
                  <span className="mode-tag" data-tone="agent">
                    READY
                  </span>
                </div>
              )}
              <button className="button button--primary" onClick={() => setStep(2)} type="button">
                {humanPlayEnabled
                  ? zh
                    ? "确认控制方式 →"
                    : "Confirm control →"
                  : zh
                    ? "继续匹配对手 →"
                    : "Continue to matchmaking →"}
              </button>
            </section>
          )}
          {step === 2 && fleet && (
            <section>
              <p className="eyebrow">03 / {fleetReady ? "READY" : "SETUP"}</p>
              <h2>
                {fleetReady
                  ? zh
                    ? `${fleet.name} 已就位`
                    : `${fleet.name} is ready`
                  : zh
                    ? `${fleet.name} 需要继续配置`
                    : `${fleet.name} needs setup`}
              </h2>
              <p className="page-lede">
                {fleetReady
                  ? zh
                    ? `公开编号 ${fleet.publicId}。当前策略已经就绪，不需要 Agent Key；可以直接进入竞技场。`
                    : `Public ID ${fleet.publicId}. The current strategy is ready—no Agent Key required. Enter Arena when ready.`
                  : zh
                    ? "先在策略实验室完成当前策略配置，再进入竞技场。"
                    : "Finish the current strategy setup in Strategy Lab before entering Arena."}
              </p>
              <div className="toolbar">
                {fleetReady ? (
                  <Link
                    className="button button--primary"
                    href={`${localPath(locale, "/arena")}?control=${control}`}
                  >
                    {zh ? "进入竞技场 →" : "Enter Arena →"}
                  </Link>
                ) : (
                  <Link
                    className="button button--primary"
                    href={localPath(locale, "/strategy-lab")}
                  >
                    {zh ? "继续配置舰队 →" : "Continue fleet setup →"}
                  </Link>
                )}
                <Link className="button" href={localPath(locale, "/strategy-lab")}>
                  {zh ? "在平台内优化策略" : "Improve strategy in-platform"}
                </Link>
                <Link className="button" href={localPath(locale, "/command")}>
                  {zh ? "连接外部 Agent" : "Connect external Agent"}
                </Link>
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}
