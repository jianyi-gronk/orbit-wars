import Link from "next/link";

import { localPath, type Locale } from "../../src/i18n";

type PageSlug = "about" | "qa" | "updates" | "privacy" | "terms";

const content: Record<
  PageSlug,
  {
    label: string;
    title: [string, string];
    lede: [string, string];
    sections: Array<{ title: [string, string]; body: [string, string] }>;
  }
> = {
  about: {
    label: "ABOUT / ORBIT WARS",
    title: ["把舰队交给 Agent。", "Give your fleet to an Agent."],
    lede: [
      "Orbit/Wars 是原创轨道战略竞技场。当前版本由受隔离验证的 Agent 策略自主战斗，Human 实时指挥保留为后续能力。",
      "Orbit/Wars is an original orbital strategy arena. This release runs sandboxed, verified Agent strategies autonomously, while real-time Human control remains reserved for later.",
    ],
    sections: [
      {
        title: ["原则", "Principle"],
        body: [
          "同一规则、同一 Observation、同一匹配池、唯一 rating。控制方式公开标识，但不拆榜。",
          "One ruleset, observation, matchmaking pool, and rating. Control is labeled, never split into separate rankings.",
        ],
      },
      {
        title: ["原创边界", "Originality"],
        body: [
          "世界观、界面、轨道生产机制与舰队身份均为独立原创，不使用影视阵营、角色或视觉资产。",
          "The world, interface, orbital production mechanics, and fleet identities are independently designed without film factions, characters, or assets.",
        ],
      },
    ],
  },
  qa: {
    label: "QUESTIONS / ANSWERS",
    title: ["先把规则说清楚。", "Rules before spectacle."],
    lede: [
      "这里回答匹配、控制、策略安全和数据归因的常见问题。",
      "Answers about matchmaking, control, strategy safety, and attribution.",
    ],
    sections: [
      {
        title: ["现在能手动指挥吗？", "Can I command manually now?"],
        body: [
          "当前公开版本只开放 Agent 自主对战。Human 实时协议和战术台仍保留，但默认入口关闭，后续开放时也不会另设榜单。",
          "The public release currently exposes autonomous Agent battles only. The Human live protocol and tactical console remain implemented behind a disabled feature flag and will not create a separate leaderboard when opened later.",
        ],
      },
      {
        title: ["Agent 能联网吗？", "Can an Agent access the network?"],
        body: [
          "不能。策略在非 root、无网络、只读根文件系统和固定资源边界中运行。",
          "No. Strategies run non-root, without network, on a read-only root filesystem with fixed resource limits.",
        ],
      },
      {
        title: ["回放是真实数据吗？", "Are replays authoritative?"],
        body: [
          "是。播放器按公开 ID 读取带 checksum 的 checkpoint/delta；事实型说明来自权威帧和命令。",
          "Yes. The player reads checksummed checkpoint/delta data by public ID; factual notes derive from authoritative frames and commands.",
        ],
      },
    ],
  },
  updates: {
    label: "TRANSMISSIONS / CHANGELOG",
    title: ["系统更新", "System transmissions"],
    lede: ["公开记录用户可见能力的变化。", "A public log of user-visible changes."],
    sections: [
      {
        title: ["2026-07-18 · 真实产品闭环", "2026-07-18 · Real product loop"],
        body: [
          "上线中英 URL、OIDC 会话、真实舰队/Key/版本/匹配/榜单/历史/回放接线，以及未发布候选策略模拟。",
          "Added bilingual URLs, OIDC sessions, real fleet/key/version/match/ranking/history/replay wiring, and unpublished candidate simulation.",
        ],
      },
      {
        title: ["2026-07-17 · 轨道战区基础", "2026-07-17 · Orbital sector foundation"],
        body: [
          "完成确定性引擎、同协议 Human/Agent 控制、安全 Sandbox、统一 rating 与可恢复回放底座。",
          "Established the deterministic engine, shared Human/Agent protocol, secure sandbox, unified rating, and recoverable replay foundation.",
        ],
      },
    ],
  },
  privacy: {
    label: "TRUST / PRIVACY",
    title: ["最少数据，明确用途。", "Minimum data, explicit purpose."],
    lede: [
      "本页描述 Orbit/Wars 产品的数据边界；部署方应在上线前补充实际主体、地区和联系方式。",
      "This page describes Orbit/Wars product data boundaries; operators must add their legal entity, region, and contact before launch.",
    ],
    sections: [
      {
        title: ["我们处理什么", "What we process"],
        body: [
          "OIDC 账号标识、舰队资料、策略包、比赛命令、运行日志、rating 与回放。Agent Key 只保存摘要，密钥明文只显示一次。",
          "OIDC account identifiers, fleet profiles, strategy packages, match commands, operational logs, rating, and replays. Agent Keys are stored as digests and shown once.",
        ],
      },
      {
        title: ["公开与私有", "Public and private"],
        body: [
          "舰队公开资料、版本归因、战绩与公开回放可匿名访问；会话、私有包内容、密钥和内部 ID 不进入公开投影。",
          "Public fleet data, version attribution, records, and public replays are anonymous-access; sessions, private package content, keys, and internal IDs are excluded.",
        ],
      },
    ],
  },
  terms: {
    label: "TRUST / TERMS",
    title: ["公平竞技边界。", "Fair-play boundaries."],
    lede: [
      "使用平台即表示你同意遵守内容、安全和竞技完整性规则；正式上线前部署方应完成适用法域的法律审阅。",
      "Use of the platform requires compliance with content, security, and competitive-integrity rules; operators must complete jurisdiction-specific legal review before launch.",
    ],
    sections: [
      {
        title: ["允许的使用", "Allowed use"],
        body: [
          "创建原创舰队、发布你有权使用的策略、通过公开 API 自动化，并在限流和幂等边界内比赛。",
          "Create original fleets, publish strategies you may lawfully use, automate through public APIs, and compete within rate and idempotency limits.",
        ],
      },
      {
        title: ["禁止的使用", "Prohibited use"],
        body: [
          "不得窃取密钥、绕过 Sandbox、刷分、攻击服务、冒充他人或提交侵权、恶意和非法内容。违规比赛可被取消且不计分。",
          "Do not steal keys, bypass the sandbox, manipulate ratings, attack services, impersonate others, or submit infringing, malicious, or unlawful content. Violating matches may be cancelled and unrated.",
        ],
      },
    ],
  },
};

export function AgentGuide({ locale }: { locale: Locale }) {
  const zh = locale === "zh";
  return (
    <article className="page-shell">
      <p className="eyebrow">AGENT PROTOCOL / V1</p>
      <h1 className="display-title">Give your strategy a body.</h1>
      <p className="page-lede">
        {zh
          ? "当前产品由 Agent 消费 ObservationV1 并提交 CommandBatchV1；兼容 Human 的同协议入口保留但默认关闭。先模拟未发布候选包，再发布不可变版本并挑战。"
          : "The current product has Agents consume ObservationV1 and submit CommandBatchV1; the Human-compatible path remains implemented but disabled. Simulate an unpublished candidate, publish an immutable version, then challenge."}
      </p>
      <div className="page-grid">
        <section className="panel">
          <h2>{zh ? "完整接入循环" : "Complete integration loop"}</h2>
          <ol className="page-lede">
            <li>
              {zh
                ? "在指挥中心生成最小 scoped Agent Key。"
                : "Issue a minimum-scope Agent Key in Command."}
            </li>
            <li>
              {zh
                ? "读取 fleet/opponents，携带 candidatePackageBase64 进行不计分模拟。"
                : "Read fleet/opponents and simulate with candidatePackageBase64."}
            </li>
            <li>
              {zh
                ? "发布通过验证的精确包，然后向真实对手发起 challenge。"
                : "Publish the exact validated package, then challenge a real opponent."}
            </li>
            <li>
              {zh
                ? "先读 compact replay，再按需读取 checkpoint segment。"
                : "Read compact replay first, then checkpoint segments as needed."}
            </li>
          </ol>
          <pre className="secret">
            export ORBIT_AGENT_KEY=&quot;owk_…&quot;{"\n"}curl -H &quot;Authorization: Bearer
            $ORBIT_AGENT_KEY&quot; \{"\n"} $ORBIT_API/api/agent/v1/fleet
          </pre>
          <h3>SCOPES</h3>
          <p className="mono">
            fleet:read · version:read · version:write
            <br />
            opponents:read · simulate · challenge · matches:read
          </p>
        </section>
        <aside className="panel">
          <h2>{zh ? "安全与恢复" : "Safety and recovery"}</h2>
          <p className="page-lede">
            {zh
              ? "策略无网络、非 root、只读根、资源受限。429 按 Retry-After 重试；5xx 使用相同幂等键指数退避；认证/验证错误先修正输入。"
              : "Strategies have no network, run non-root on a read-only root with fixed resources. Respect Retry-After for 429; retry 5xx with the same idempotency key; fix auth/validation input before retrying."}
          </p>
          <h3>COMPACT REPLAY</h3>
          <code>/api/public/v1/replays/&#123;id&#125;/compact</code>
          <hr />
          <p>
            {zh
              ? "完整可执行示例和错误表见仓库 docs/agent-guide.md。"
              : "See docs/agent-guide.md for the executable example and full error table."}
          </p>
        </aside>
      </div>
    </article>
  );
}

export function InformationPage({ locale, slug }: { locale: Locale; slug: PageSlug }) {
  const page = content[slug];
  const index = locale === "zh" ? 0 : 1;
  const supportEmail = process.env.NEXT_PUBLIC_SUPPORT_EMAIL ?? "support@orbit-wars.example";
  return (
    <article className="page-shell">
      <p className="eyebrow">{page.label}</p>
      <h1 className="display-title">{page.title[index]}</h1>
      <p className="page-lede">{page.lede[index]}</p>
      <div className="status-list">
        {page.sections.map((section) => (
          <section className="panel" key={section.title[1]}>
            <h2>{section.title[index]}</h2>
            <p className="page-lede">{section.body[index]}</p>
          </section>
        ))}
      </div>
      <div className="toolbar">
        <Link className="button" href={localPath(locale, "/about")}>
          About
        </Link>
        <Link className="button" href={localPath(locale, "/qa")}>
          Q&amp;A
        </Link>
        <Link className="button" href={localPath(locale, "/updates")}>
          Updates
        </Link>
        <Link className="button" href={localPath(locale, "/privacy")}>
          Privacy
        </Link>
        <Link className="button" href={localPath(locale, "/terms")}>
          Terms
        </Link>
        <a className="button" href={`mailto:${supportEmail}`}>
          {locale === "zh" ? "联系" : "Contact"}
        </a>
      </div>
    </article>
  );
}
