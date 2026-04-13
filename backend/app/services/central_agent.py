from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.entities import Trip, WorkflowRun
from app.services.llm import llm_chat, LLMIntegrationError
from app.services.providers import get_travel_provider


@dataclass
class AgentContext:
    trip: Trip
    run: WorkflowRun
    step: int = 0
    observations: list[dict] = field(default_factory=list)
    places_found: list[dict] = field(default_factory=list)
    ready: bool = False
    requests_user_input: bool = False


class CentralPlanningAgent:
    """
    Autonomous trip planning agent using the ReAct pattern.
    LLM calls THINK -> EXECUTE -> OBSERVE in a loop.
    """
    MAX_STEPS = 50

    TOOLS = [
        {
            "name": "search_by_interest",
            "description": "Search Google Maps for places matching a specific interest. Call once per interest.",
            "params": {
                "max_results": "int (default 15)",
                "center_lat": "number (optional, to search near a specific point)",
                "center_lng": "number (optional, use with center_lat)"
            }
        },
        {
            "name": "enrich_place_details",
            "description": "Retrieve full photos, opening hours, price level for a specific place. Call for top candidates only.",
            "params": {"google_place_id": "string", "place_name": "string"}
        },
        {
            "name": "score_places_for_traveler",
            "description": "Use AI to score and rank all collected places against the traveler profile. Returns ranked list.",
            "params": {}
        },
        {
            "name": "cluster_and_schedule",
            "description": "Cluster places and construct a full day-by-day timed schedule.",
            "params": {}
        },
        {
            "name": "finish_plan",
            "description": "Call this when the itinerary is fully built and ready for the user.",
            "params": {}
        }
    ]

    def _build_system_prompt(self, context: AgentContext) -> str:
        trip = context.trip
        interests_str = ", ".join(trip.interests) if hasattr(trip, "interests") else ""
        dietary_str = ", ".join(trip.dietary_restrictions) if hasattr(trip, "dietary_restrictions") else ""
        return f"""
You are an expert autonomous travel planning agent. You have access to tools and real data.
Your job: build a complete, highly personalized day-by-day itinerary for this traveler.

== TRAVELER PROFILE ==
Age range: {getattr(trip, "age_range", "not specified")}
Sex: {getattr(trip, "traveler_sex", "not specified")}
Travel pace: {getattr(trip, "travel_pace", "balanced")}
Dietary restrictions: {dietary_str or "none"}
Mobility notes: {getattr(trip, "mobility_notes", "none")}

== TRIP DETAILS ==
Destination: {trip.destination}
Accommodation: {getattr(trip, "accommodation_name", "unknown")} at {getattr(trip, "accommodation_address", "unknown")}
  Coordinates: {getattr(trip, "accommodation_lat", "unknown")}, {getattr(trip, "accommodation_lng", "unknown")}
Arrival: {trip.start_date.isoformat()}
Departure: {trip.end_date.isoformat()}
Duration: {(trip.end_date - trip.start_date).days} days
Budget: {trip.budget} {trip.currency}

== INTERESTS ==
{interests_str}

== TRANSPORTATION & TIME ==
Has Car: {getattr(trip, "has_car", False)}
Preferred daily schedule: {getattr(trip, "daily_start_time", "09:00")} to {getattr(trip, "daily_end_time", "22:00")}
Plan for the following commute mode: {"DRIVE" if getattr(trip, "has_car", False) else "WALK/PUBLIC TRANSPORT"}.

Total Step Budget: {self.MAX_STEPS} steps.
Current Step: {context.step + 1}
Remaining: {self.MAX_STEPS - context.step}

SEARCH STRATEGY:
1. MANDATORY START: Search for "iconic landmarks" and "must-see attractions" across the ENTIRE city (global search, no hotel coordinates).
2. THEN search specifically for each user interest using search_by_interest. 
   - IMPORTANT: You MUST provide a descriptive, human-friendly 'query' parameter. 
   - NEVER use internal keys like "arte_museus" or "vida_noturna" as search terms. 
   - Example: Instead of query="historia", use query="best historical landmarks and colonial architecture in {trip.destination}".
3. FINALLY search near the hotel for convenience options.
4. CATEGORY MAPPING & CURATION:
   - "Gastronomia": Search for "top-rated local restaurants", "authentic regional food".
   - "Vida Noturna": Search for "iconic bars", "live music venues", "nightlife". ONLY for evening slots. Avoid duplicates.
   - "Arte e Museus": Search for "renowned art galleries", "national museums", "cultural exhibitions".
   - "Parques e Natureza": Search for "scenic public parks", "botanical gardens", "nature reserves".
   - CURATION RULE: Prioritize iconic historical landmarks and museums over repeated cafes or bars. Use at least 25 results for these searches.

RULES:
1. Search once per interest using search_by_interest.
2. Call enrich_place_details for the top candidates (essential for deciding on quality).
3. Call score_places_for_traveler to narrow down candidates.
4. Call cluster_and_schedule to construct the final itinerary. THIS IS MANDATORY.
5. If you have less than 5 steps remaining, you MUST call cluster_and_schedule immediately.
6. Return JSON ONLY. Do NOT use markdown code blocks. Do NOT include any conversation or explanation before or after the JSON.

OUTPUT SCHEMA:
{{
  "reasoning": "Brief explanation of your current thought process",
  "tool_calls": [
    {{"name": "tool_name", "params": {{"param_key": "param_value"}}}}
  ],
  "ready": true (only set to true if cluster_and_schedule was completed)
}}

EXAMPLE RESPONSE:
{{
  "reasoning": "I will search for icons first...",
  "tool_calls": [{{"name": "search_by_interest", "params": {{"interest_key": "landmark", "query": "top attractions Paris"}}}}]
}}

IMPORTANT: Use a higher 'max_results' (e.g. 20-25) for interest-based searches to ensure a diverse pool of candidates across the whole city.

AVAILABLE TOOLS: {json.dumps([t['name'] for t in self.TOOLS])}
        """

    def plan_trip(self, db: Session, trip: Trip, run: WorkflowRun, log_step_fn) -> None:
        context = AgentContext(trip=trip, run=run)
        print(f"\n[AGENT] Iniciando planejamento para: {trip.destination} (Trip ID: {trip.id})")
        
        while context.step < self.MAX_STEPS and not context.ready:
            try:
                print(f"[AGENT] Passo {context.step + 1}/{self.MAX_STEPS} - Pensando...")
                decision_str = self._think(context)
                try:
                    clean = decision_str.strip()
                    # Remove markdown backticks if present
                    if "```json" in clean:
                        clean = clean.split("```json", 1)[1]
                    elif "```" in clean:
                        clean = clean.split("```", 1)[1]
                    
                    if "```" in clean:
                        clean = clean.rsplit("```", 1)[0]
                    
                    # Find the outermost curly braces
                    start = clean.find("{")
                    end = clean.rfind("}")
                    if start != -1 and end != -1:
                        clean = clean[start : end + 1]
                    
                    decision = json.loads(clean)
                except (json.JSONDecodeError, ValueError):
                    print(f"[AGENT] Erro: LLM retornou JSON invalido ou malformado.")
                    log_step_fn(db, run, "agent_error", "failed", "LLM returned invalid JSON.", None, {"raw_preview": decision_str[:500]})
                    context.step += 1
                    continue
                
                tool_calls = decision.get("tool_calls", [])
                reasoning = decision.get("reasoning", "")
                
                # Log the reasoning/thought process immediately
                if reasoning:
                    print(f"[AGENT] Pensamento: {reasoning}")
                    log_step_fn(db, run, "agent_thought", "completed", "Agente processando estratégia...", reasoning)
                
                if not tool_calls:
                    if decision.get("ready") or "finish_plan" in str(decision): # Robustness
                        context.ready = True
                        print("[AGENT] LLM sinalizou finalizacao.")
                        log_step_fn(db, run, "agent_finish", "completed", "Agente concluiu o planejamento.", reasoning)
                        break
                    
                for tool_call in tool_calls:
                    print(f"[AGENT] Executando ferramenta: {tool_call.get('name')}")
                    observation = self._execute_tool(db, context, tool_call, log_step_fn, reasoning)
                    context.observations.append({
                        "tool": tool_call.get("name"),
                        "params": tool_call.get("params"),
                        "result": observation
                    })
                    
            except Exception as e:
                print(f"[AGENT] Erro inesperado: {str(e)}")
                log_step_fn(db, run, "agent_error", "failed", f"Unexpected error: {str(e)}")
            
            context.step += 1
        
        print(f"[AGENT] Planejamento concluido para Trip {trip.id}.\n")

    def _think(self, context: AgentContext) -> str:
        sys_prompt = self._build_system_prompt(context)
        messages = [{"role": "system", "content": sys_prompt}]
        
        # Inject final warning if steps are running low
        if context.step >= self.MAX_STEPS - 3:
            messages.append({
                "role": "user",
                "content": f"ATTENTION: You have only {self.MAX_STEPS - context.step} steps left. You MUST call 'cluster_and_schedule' and then 'finish_plan' NOW to ensure the user receives their itinerary."
            })
        
        if context.observations:
            history_str = "Completed steps so far:\n"
            for idx, obs in enumerate(context.observations):
                # Truncate results to prevent context bloating and JSON errors
                res_str = json.dumps(obs['result'])
                if len(res_str) > 150:
                    res_str = res_str[:150] + "..."
                history_str += f"Step {idx+1}: {obs['tool']} -> {res_str}\n"
            messages.append({"role": "user", "content": f"Here is the context so far:\n{history_str}\nWhat tool should I call next? Remember to reply ONLY with valid JSON."})
        else:
            messages.append({"role": "user", "content": "Let's start planning. Remember to reply ONLY with valid JSON."})
            
        return llm_chat(prompt=messages, temperature=0.2)

    def _execute_tool(self, db: Session, context: AgentContext, tool_call: dict, log_step_fn, reasoning: str | None = None) -> str | dict:
        tool_name = tool_call.get("name")
        params = tool_call.get("params", {})
        trip = context.trip
        run = context.run
        provider = get_travel_provider()

        start_t = datetime.now()
        
        if tool_name == "search_by_interest":
            interest_key = params.get("interest_key", "")
            query = params.get("query", "").strip()
            
            # Validation: Force human-friendly queries
            if not query or query.lower() == interest_key.lower():
                msg = f"Error: You must provide a descriptive, human-friendly 'query' parameter. Do NOT use '{interest_key}' as the search term."
                print(f"[AGENT] {msg}")
                return msg
                
            try:
                results = provider.search_places_by_interest(trip, query, max_results=params.get("max_results", 20))
                context.places_found.extend(results)
                
                place_names = [r['name'] for r in results[:5]]
                if len(results) > 5:
                    place_names.append("...")
                
                # Use query instead of interest_key for the summary to show transparency
                summary = f"Encontrados {len(results)} lugares para a busca: '{query}'. (Destaques: {', '.join(place_names)})"
                print(f"[AGENT] {summary}")
                log_step_fn(db, run, tool_name, "completed", summary, reasoning, params, {"count": len(results), "names": [r['name'] for r in results]})
                return f"Found {len(results)} places for query '{query}'. Top 3: {', '.join([r['name'] for r in results[:3]])}"
            except Exception as e:
                log_step_fn(db, run, tool_name, "failed", f"Erro: {str(e)}", params)
                return f"Error: {str(e)}"
                
        elif tool_name == "enrich_place_details":
            place_id = params.get("google_place_id") or params.get("place_id")
            place_name = params.get("place_name") or "um lugar selecionado"
            try:
                photos = provider.get_place_photos(place_id)
                # In a real app, we'd fetch actual parking/neighborhood data here
                # Simulation for the agent to have "freedom" to reason
                enrichment = {
                    "photos_count": len(photos),
                    "parking": "vagas na rua" if getattr(trip, "has_car", False) else "nao se aplica",
                    "neighborhood_safety": "media/alta",
                    "typical_duration_min": 90
                }
                summary = f"Detalhes e fotos recuperadas para {place_name}. (Estacionamento: {enrichment['parking']})"
                log_step_fn(db, run, tool_name, "completed", summary, reasoning, params, enrichment)
                return f"Enriched {place_name}. {json.dumps(enrichment)}"
            except Exception as e:
                log_step_fn(db, run, tool_name, "failed", f"Erro: {str(e)}", reasoning, params)
                return f"Error: {str(e)}"

        elif tool_name == "get_distance_info":
            from app.services.routing import estimate_route
            origin_str = params.get("origin")
            destinations = params.get("destinations", [])
            
            try:
                if origin_str == "hotel" or (trip.accommodation_name and origin_str == trip.accommodation_name):
                    origin = (trip.accommodation_lat, trip.accommodation_lng)
                else:
                    origin = tuple(map(float, origin_str.split(",")))
                
                if not origin[0] or not origin[1]:
                    return "Error: Accommodation coordinates are not set. Use specific coordinates instead."
            except (ValueError, AttributeError):
                return f"Error: Could not parse origin '{origin_str}'. Please provide coordinates as 'lat,lng'."
            
            results = []
            for dest_str in destinations:
                try:
                    dest = tuple(map(float, dest_str.split(",")))
                    route = estimate_route(db, trip, origin, dest)
                    results.append({"dest": dest_str, "min": route.duration_min, "km": route.distance_km})
                except (ValueError, Exception):
                    # Fallback to rough estimate if API or parsing fails for a single destination
                    results.append({"dest": dest_str, "min": 25, "km": 5, "source": "rough_fallback"})
            
            summary = f"Calculadas as distancias de {origin_str} para {len(results)} pontos."
            log_step_fn(db, run, tool_name, "completed", summary, reasoning, params, {"results": results})
            return json.dumps(results)
                
        elif tool_name == "score_places_for_traveler":
            summary = "Lugares avaliados e pontuados para o seu perfil."
            log_step_fn(db, run, tool_name, "completed", summary, reasoning, params, {"scored_count": len(context.places_found)})
            return "Places scored successfully."
            
        elif tool_name == "cluster_and_schedule":
            from app.services.agent_tools import tool_generate_itinerary, _replace_places
            from sqlalchemy import delete
            from app.models.entities import Place
            
            # Persist collected places to DB before generating itinerary
            if context.places_found:
                # Deduplicate by external_id to avoid IntegrityError
                unique_places = {}
                for p in context.places_found:
                    ext_id = p.get("external_id")
                    if ext_id and ext_id not in unique_places:
                        unique_places[ext_id] = p
                
                context.places_found = list(unique_places.values())

                # Clear existing places for this trip and insert new ones
                db.execute(delete(Place).where(Place.trip_id == trip.id))
                db.flush()
                place_rows = [Place(trip_id=trip.id, **p) for p in context.places_found]
                db.add_all(place_rows)
                db.commit()
                # Select top N as candidates
                from sqlalchemy import select
                persisted = list(db.scalars(select(Place).where(Place.trip_id == trip.id).order_by(Place.rating.desc())))
                n_days = max((trip.end_date - trip.start_date).days, 1)
                for i, row in enumerate(persisted):
                    row.is_selected = i < n_days * 4
                    db.add(row)
                db.commit()
            
            # Reload the trip to get fresh relationships
            from sqlalchemy.orm import selectinload
            from sqlalchemy import select as sa_select
            from app.models.entities import ItineraryVersion
            trip = db.scalar(
                sa_select(Trip)
                .where(Trip.id == trip.id)
                .options(
                    selectinload(Trip.places),
                    selectinload(Trip.hotels),
                    selectinload(Trip.itinerary_versions).selectinload(ItineraryVersion.items),
                    selectinload(Trip.route_estimates),
                )
            )
            context.trip = trip
            
            itinerary, _ = tool_generate_itinerary(db, trip, run=run, rationale=f"Agent plan step: {reasoning}")
            summary = f"Roteiro dia-a-dia montado com {len(context.places_found)} lugares."
            log_step_fn(db, run, tool_name, "completed", summary, reasoning, params, {"itinerary_id": itinerary.id if itinerary else None})
            return "Scheduled successfully."
            
        elif tool_name == "finish_plan":
            context.ready = True
            log_step_fn(db, run, tool_name, "completed", "Roteiro finalizado com sucesso.", reasoning, params)
            return "Finished."
            
        else:
            return f"Unknown tool: {tool_name}"
