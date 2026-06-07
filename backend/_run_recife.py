"""Ad-hoc runner: regenerate the Recife trip (id=3) with the freed agent and
print the full tool-call trace. Not part of the app — for manual verification."""
import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from app.core.database import SessionLocal
from app.models.entities import Trip, User, WorkflowRun
from app.services.central_mind import CentralMind

TRIP_ID = 3
db = SessionLocal()
trip = db.get(Trip, TRIP_ID)
user = db.get(User, trip.user_id)

# Archive any existing active itinerary so the agent builds fresh.
for v in trip.itinerary_versions:
    if v.status == "active":
        v.status = "archived"
        db.add(v)
db.commit()

run = WorkflowRun(trip_id=trip.id, run_type="generate", status="running")
db.add(run); db.commit(); db.refresh(run)

trace = []
def log_step(db_, run_, step_key, status_name, summary, reasoning=None, input_json=None, output_json=None):
    trace.append((step_key, status_name, summary))
    line = f"[{len(trace):>3}] {step_key:<22} {status_name:<9} {str(summary)[:160]}"
    print(line, flush=True)

print(f"=== Planning Recife trip {trip.id} ({trip.start_date} -> {trip.end_date}) ===", flush=True)
mind = CentralMind(user)
try:
    mind.plan_trip(db, trip, run, log_step)
except Exception as e:
    import traceback; traceback.print_exc()

# Reload + print resulting itinerary
db.expire_all()
trip = db.get(Trip, TRIP_ID)
active = next((v for v in reversed(trip.itinerary_versions) if v.status == "active"), None)
print("\n=== RESULTING ITINERARY ===", flush=True)
if not active:
    print("NO ACTIVE ITINERARY PRODUCED", flush=True)
else:
    from collections import defaultdict
    by_day = defaultdict(list)
    for it in active.items:
        by_day[it.date].append(it)
    for day in sorted(by_day):
        print(f"\n{day} — {len(by_day[day])} stops", flush=True)
        for it in sorted(by_day[day], key=lambda x: x.start_time):
            print(f"   {it.start_time.strftime('%H:%M')}-{it.end_time.strftime('%H:%M')}  "
                  f"[{it.item_type}] {it.title}  (travel {it.travel_time_min}min)", flush=True)
    # Run the analyzer on the final result
    from app.services.itinerary_quality import analyze_itinerary
    rep = analyze_itinerary(trip, active, getattr(trip, "travel_pace", None))
    print(f"\n=== QUALITY: blocking={rep['blocking_count']} warning={rep['warning_count']} "
          f"finalizable={rep['is_finalizable']} ===", flush=True)
    for d in rep["days"]:
        if d["issues"]:
            print(f"  {d['date']}: " + "; ".join(f"[{i['severity']}] {i['code']}" for i in d["issues"]), flush=True)

# Trace summary
from collections import Counter
print("\n=== TOOL-CALL COUNTS ===", flush=True)
for k, c in Counter(t[0] for t in trace).most_common():
    print(f"  {k}: {c}", flush=True)
db.close()
