import { redirect } from "next/navigation";

export default async function LeaderboardPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string>>;
}) {
  const query = new URLSearchParams(await searchParams).toString();
  redirect(`/zh/leaderboard${query ? `?${query}` : ""}`);
}
