import { redirect } from "next/navigation";

export default async function FleetProfilePage({
  params,
}: {
  params: Promise<{ publicId: string }>;
}) {
  const { publicId } = await params;
  redirect(`/zh/fleet/${encodeURIComponent(publicId)}`);
}
