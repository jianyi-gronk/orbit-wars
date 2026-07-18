import { redirect } from "next/navigation";

export default async function ArenaPage({
  searchParams,
}: {
  searchParams: Promise<{ control?: string }>;
}) {
  const { control } = await searchParams;
  redirect(`/zh/arena${control ? `?control=${encodeURIComponent(control)}` : ""}`);
}
