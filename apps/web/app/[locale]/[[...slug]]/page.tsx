import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { StartFlow } from "../../start/StartFlow";
import { CommandCenter } from "../../command/CommandCenter";
import { ArenaForm } from "../../arena/ArenaForm";
import { StrategyLab } from "../../strategy-lab/StrategyLab";
import { LiveBattle } from "../../../components/battle/LiveBattle";
import { ReplayPlayer } from "../../../components/battle/ReplayPlayer";
import { HomeExperience } from "../../../components/product/HomeExperience";
import { SiteHeader } from "../../../components/product/SiteHeader";
import {
  FleetProfileView,
  HistoryView,
  LeaderboardView,
} from "../../../components/product/PublicCompetition";
import { AgentGuide, InformationPage } from "../../../components/product/InformationPages";
import { humanPlayEnabled } from "../../../src/features";
import { isLocale, type Locale } from "../../../src/i18n";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string; slug?: string[] }>;
}): Promise<Metadata> {
  const { locale: rawLocale, slug = [] } = await params;
  const locale: Locale = isLocale(rawLocale) ? rawLocale : "zh";
  const route = slug.join("/");
  const zh = locale === "zh";
  const titles: Record<string, [string, string]> = {
    "agent-guide": ["Agent 接入指南", "Agent Guide"],
    arena: ["竞技场", "Arena"],
    command: ["舰队指挥中心", "Fleet Command"],
    history: ["公开对局历史", "Public Match History"],
    leaderboard: ["统一排行榜", "Unified Leaderboard"],
    start: ["创建舰队", "Create Fleet"],
    "strategy-lab": ["策略实验室", "Strategy Lab"],
  };
  const title = titles[route]?.[zh ? 0 : 1] ?? (zh ? "轨道战略竞技场" : "Orbital Strategy Arena");
  const suffix = route ? `/${route}` : "";
  return {
    title,
    description: zh
      ? "创建原创舰队，让 Agent 在可验证的轨道战场中训练、排位与进化。"
      : "Create an original fleet and let its Agent train, rank, and evolve in a verifiable orbital arena.",
    alternates: {
      canonical: `/${locale}${suffix}`,
      languages: { "zh-CN": `/zh${suffix}`, en: `/en${suffix}` },
    },
  };
}

function Home({ locale }: { locale: Locale }) {
  return (
    <main className="product-home">
      <SiteHeader locale={locale} />
      <HomeExperience locale={locale} />
    </main>
  );
}

export default async function LocalizedPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string; slug?: string[] }>;
  searchParams: Promise<{ control?: string; period?: string; sort?: string }>;
}) {
  const { locale: rawLocale, slug = [] } = await params;
  if (!isLocale(rawLocale)) notFound();
  const locale = rawLocale as Locale;
  const route = slug.join("/");
  if (!route) return <Home locale={locale} />;
  if (route === "start")
    return (
      <main className="product-page">
        <SiteHeader locale={locale} />
        <div className="page-shell page-grid">
          <section>
            <p className="eyebrow">ENLISTMENT / OPEN CHANNEL</p>
            <h1 className="display-title">Make a fleet. Leave a trace.</h1>
            <p className="page-lede">
              {locale === "zh"
                ? humanPlayEnabled
                  ? "登录后建立一支真实持久化的原创舰队，再决定由你或 Agent 控制。"
                  : "登录后建立一支真实持久化的原创舰队，并让 Agent 带它进入竞技场。"
                : humanPlayEnabled
                  ? "Sign in, establish a persistent original fleet, then choose Human or Agent control."
                  : "Sign in, establish a persistent original fleet, and deploy its Agent into the arena."}
            </p>
          </section>
          <StartFlow locale={locale} />
        </div>
      </main>
    );
  if (route === "command")
    return (
      <main className="product-page">
        <SiteHeader locale={locale} />
        <CommandCenter locale={locale} />
      </main>
    );
  if (route === "strategy-lab")
    return (
      <main className="product-page">
        <SiteHeader locale={locale} />
        <div className="page-shell">
          <StrategyLab locale={locale} />
        </div>
      </main>
    );
  if (route === "arena") {
    const query = await searchParams;
    const initialControl = humanPlayEnabled && query.control === "human" ? "human" : "agent";
    return (
      <main className="product-page">
        <SiteHeader locale={locale} />
        <div className="page-shell page-grid">
          <section>
            <p className="eyebrow">ARENA / ONE POOL</p>
            <h1 className="display-title">
              {locale === "zh" ? "三步开战。" : "Battle in three steps."}
            </h1>
            <p className="page-lede">
              {locale === "zh"
                ? humanPlayEnabled
                  ? "选控制方式、选模式、确认对手，然后立即进入战场。Human 与 Agent 共用匹配池与排名。"
                  : "选择训练或排位，确认对手，然后让当前 Agent 策略自主完成比赛。"
                : humanPlayEnabled
                  ? "Choose control, choose a mode, confirm a rival, then enter the battlefield. Human and Agent share one pool and ranking."
                  : "Choose training or ranked, confirm a rival, then let the current Agent strategy run the match autonomously."}
            </p>
          </section>
          <ArenaForm initialControl={initialControl} locale={locale} />
        </div>
      </main>
    );
  }
  if (slug[0] === "battle" && slug[1]) return <LiveBattle locale={locale} matchId={slug[1]} />;
  if (route === "leaderboard") {
    const query = await searchParams;
    const period = ["today", "week", "all"].includes(query.period ?? "") ? query.period! : "all";
    const control = ["human", "agent"].includes(query.control ?? "") ? query.control! : "all";
    const sort = ["score", "win_rate", "wins"].includes(query.sort ?? "")
      ? query.sort!
      : period === "all"
        ? "score"
        : "win_rate";
    return (
      <main className="product-page">
        <SiteHeader locale={locale} />
        <LeaderboardView control={control} locale={locale} period={period} sort={sort} />
      </main>
    );
  }
  if (slug[0] === "fleet" && slug[1])
    return (
      <main className="product-page">
        <SiteHeader locale={locale} />
        <FleetProfileView locale={locale} publicId={slug[1]} />
      </main>
    );
  if (route === "history")
    return (
      <main className="product-page">
        <SiteHeader locale={locale} />
        <HistoryView locale={locale} />
      </main>
    );
  if (slug[0] === "replay" && slug[1]) return <ReplayPlayer locale={locale} publicId={slug[1]} />;
  if (route === "agent-guide")
    return (
      <main className="product-page">
        <SiteHeader locale={locale} />
        <AgentGuide locale={locale} />
      </main>
    );
  if (["about", "qa", "updates", "privacy", "terms"].includes(route))
    return (
      <main className="product-page">
        <SiteHeader locale={locale} />
        <InformationPage
          locale={locale}
          slug={route as "about" | "qa" | "updates" | "privacy" | "terms"}
        />
      </main>
    );
  notFound();
}
