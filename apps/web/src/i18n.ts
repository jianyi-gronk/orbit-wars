export const locales = ["zh", "en"] as const;
export type Locale = (typeof locales)[number];

export function isLocale(value: string): value is Locale {
  return locales.includes(value as Locale);
}

export function localeFrom(value: string | undefined): Locale {
  return value && isLocale(value) ? value : "zh";
}

export function localPath(locale: Locale, path = "/"): string {
  const normalized = path === "/" ? "" : path.startsWith("/") ? path : `/${path}`;
  return `/${locale}${normalized}`;
}

export function swapLocale(pathname: string, locale: Locale): string {
  const segments = pathname.split("/");
  if (isLocale(segments[1] ?? "")) segments[1] = locale;
  else segments.splice(1, 0, locale);
  return segments.join("/") || `/${locale}`;
}

export const messages = {
  zh: {
    nav: {
      arena: "竞技场",
      command: "指挥中心",
      create: "创建舰队",
      history: "对局历史",
      leaderboard: "统一榜单",
      login: "登录",
      logout: "退出登录",
    },
    common: {
      agent: "Agent",
      back: "返回",
      empty: "暂无数据",
      error: "请求失败",
      human: "Human",
      loading: "正在读取权威数据…",
      retry: "重试",
      training: "训练",
      ranked: "排位",
    },
    replay: {
      loading: "正在加载对局记录…",
    },
    errors: {
      authentication_required: "请先登录再继续。",
      fleet_already_exists: "此账号已经拥有舰队。",
      fleet_invalid_content: "舰队资料不符合内容或长度要求。",
      fleet_not_found: "当前账号尚未建立舰队。",
      match_not_found: "没有找到可用比赛或匹配对手。",
      match_human_training_only: "Human Beta 当前仅支持训练赛。",
      matchmaking_no_candidate: "暂时没有符合公平条件的对手，请稍后重试。",
      matchmaking_unavailable: "暂时没有可匹配的对手。",
      replay_not_found: "该公开回放不存在。",
      http_401: "会话不存在或已过期，请重新登录。",
      http_503: "服务暂时不可用，请稍后重试。",
      unknown: "操作未完成，请稍后重试。",
    },
  },
  en: {
    nav: {
      arena: "Arena",
      command: "Command",
      create: "Create fleet",
      history: "Match history",
      leaderboard: "Unified ranking",
      login: "Sign in",
      logout: "Sign out",
    },
    common: {
      agent: "Agent",
      back: "Back",
      empty: "No data yet",
      error: "Request failed",
      human: "Human",
      loading: "Reading authoritative data…",
      retry: "Retry",
      training: "Training",
      ranked: "Ranked",
    },
    replay: {
      loading: "Loading match record…",
    },
    errors: {
      authentication_required: "Sign in to continue.",
      fleet_already_exists: "This account already owns a fleet.",
      fleet_invalid_content: "The fleet profile does not meet content or length rules.",
      fleet_not_found: "This account has not established a fleet yet.",
      match_not_found: "No eligible match or opponent was found.",
      match_human_training_only: "Human Beta currently supports training matches only.",
      matchmaking_no_candidate: "No fair opponent is available right now. Please retry shortly.",
      matchmaking_unavailable: "No opponent is available right now.",
      replay_not_found: "This public replay does not exist.",
      http_401: "Your session is missing or expired. Please sign in again.",
      http_503: "The service is temporarily unavailable. Please try again.",
      unknown: "The operation did not finish. Please try again.",
    },
  },
} as const;

export function formatNumber(locale: Locale, value: number): string {
  return new Intl.NumberFormat(locale === "zh" ? "zh-CN" : "en").format(value);
}

export function formatDate(locale: Locale, value: string): string {
  return new Intl.DateTimeFormat(locale === "zh" ? "zh-CN" : "en", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function errorMessage(locale: Locale, code: string | undefined): string {
  const key = (code ?? "unknown").replaceAll(".", "_") as keyof (typeof messages)["zh"]["errors"];
  return messages[locale].errors[key] ?? messages[locale].errors.unknown;
}
