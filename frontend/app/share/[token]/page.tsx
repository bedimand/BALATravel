import { SharedTripView } from "@/components/shared-trip-view";

export default async function SharedTripPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return <SharedTripView token={token} />;
}
