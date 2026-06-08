import { ExportView } from "@/components/export-view";

export default async function TripExportPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ExportView tripId={id} />;
}
