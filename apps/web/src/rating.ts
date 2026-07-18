import type { CompetitiveRank } from "./api";
import { formatNumber, type Locale } from "./i18n";

const tierNames: Record<CompetitiveRank["tier"], Record<Locale, string>> = {
  bronze: { zh: "青铜", en: "Bronze" },
  silver: { zh: "白银", en: "Silver" },
  gold: { zh: "黄金", en: "Gold" },
  platinum: { zh: "铂金", en: "Platinum" },
  diamond: { zh: "钻石", en: "Diamond" },
  master: { zh: "大师", en: "Master" },
};

export function competitiveRankLabel(locale: Locale, rank: CompetitiveRank): string {
  const division = rank.division ? ` ${rank.division}` : "";
  return `${tierNames[rank.tier][locale]}${division}`;
}

export function competitiveRankPoints(locale: Locale, rank: CompetitiveRank): string {
  const points = formatNumber(locale, rank.points);
  return locale === "zh" ? `${points} 分` : `${points} pts`;
}
