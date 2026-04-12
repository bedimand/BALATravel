import { TripPlanner } from "@/components/trip-planner";

export default async function TripPlannerPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <TripPlanner tripId={id} />;
}

