import { redirect } from "next/navigation";

export default async function ReplayPage({ params }: { params: Promise<{ publicId: string }> }) {
  const { publicId } = await params;
  redirect(`/zh/replay/${encodeURIComponent(publicId)}`);
}
