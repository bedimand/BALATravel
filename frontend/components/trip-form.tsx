"use client";

import { useState, useEffect, useRef, useMemo, FormEvent } from "react";
import { useRouter } from "next/navigation";
import { setOptions, importLibrary } from "@googlemaps/js-api-loader";

import { api } from "@/lib/api";
import { useRequireAuth } from "@/lib/use-require-auth";
import { BrandLogo } from "@/components/brand-logo";

type Draft = {
  start_date: string;
  end_date: string;
  destination: string;
  accommodation_name: string;
  accommodation_address: string;
  accommodation_lat: number | null;
  accommodation_lng: number | null;
  budget: string;
  currency: string;
  interests: string[];
  age_range: string;
  traveler_sex: string;
  travel_pace: string;
  dietary_restrictions: string[];
  mobility_notes: string;
  languages: string[];
  has_car: boolean;
  daily_start_time: string;
  daily_end_time: string;
};

const INITIAL_DRAFT: Draft = {
  start_date: "",
  end_date: "",
  destination: "",
  accommodation_name: "",
  accommodation_address: "",
  accommodation_lat: null,
  accommodation_lng: null,
  budget: "2000",
  currency: "BRL",
  interests: [],
  age_range: "26-35",
  traveler_sex: "Nao informar",
  travel_pace: "Equilibrado",
  dietary_restrictions: [],
  mobility_notes: "",
  languages: ["pt"],
  has_car: false,
  daily_start_time: "09:00",
  daily_end_time: "22:00",
};

const INTEREST_OPTIONS = [
  "🍽️ Gastronomia", "🎨 Arte e Museus", "🏛️ Historia", "🎵 Vida Noturna",
  "🛍️ Compras", "🌳 Parques e Natureza", "🏖️ Praia", "🚶 Caminhadas",
  "📸 Fotografia", "☕ Cafes", "🍺 Cervejarias", "🍷 Vinhos"
];

const DIET_OPTIONS = ["Nenhuma", "Vegetariano", "Vegano", "Sem Gluten", "Halal"];
const LANG_OPTIONS = ["pt", "en", "es", "fr", "it", "de"];

export function TripForm() {
  const router = useRouter();
  useRequireAuth();
  const [step, setStep] = useState(0);
  const [loading, setLoading] = useState(false);
  const [draft, setDraft] = useState<Draft>(INITIAL_DRAFT);
  const [error, setError] = useState<string | null>(null);

  const autocompleteInputRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    let listener: google.maps.MapsEventListener | null = null;
    let isActive = true;

    if (step === 1 && autocompleteInputRef.current) {
      const initAutocomplete = async () => {
        setOptions({
          key: process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY || "",
          v: "weekly",
          libraries: ["places"],
        });
        const { Autocomplete } = (await importLibrary("places")) as google.maps.PlacesLibrary;
        
        if (!isActive || !autocompleteInputRef.current) return;

        const autocomplete = new Autocomplete(autocompleteInputRef.current, {
          types: ["establishment", "geocode"],
        });
        
        listener = autocomplete.addListener("place_changed", () => {
          const place = autocomplete.getPlace();
          if (place.geometry && place.geometry.location) {
            let city = "";
            for (const component of place.address_components || []) {
              if (component.types.includes("locality") || component.types.includes("administrative_area_level_2")) {
                city = component.long_name;
                break;
              }
            }
            if (!city && place.name) city = place.name;

            setDraft(curr => ({
              ...curr,
              destination: city,
              accommodation_name: place.name || "",
              accommodation_address: place.formatted_address || "",
              accommodation_lat: place.geometry!.location!.lat(),
              accommodation_lng: place.geometry!.location!.lng(),
            }));
          }
        });
      };
      
      initAutocomplete().catch(console.error);
    }

    return () => {
      isActive = false;
      if (listener) {
         listener.remove();
      }
      // Strict mode cleanup for ghost pac-containers
      document.querySelectorAll('.pac-container').forEach(node => {
         // Optionally wait or just remove
         if (!node.hasAttribute('data-persisted')) node.remove();
      });
    };
  }, [step]);

  const toggleInterest = (interest: string) => {
    setDraft(curr => {
      const next = curr.interests.includes(interest)
        ? curr.interests.filter(i => i !== interest)
        : [...curr.interests, interest];
      return { ...curr, interests: next };
    });
  };

  const toggleDiet = (diet: string) => {
    setDraft(curr => {
      let next = curr.dietary_restrictions;
      if (diet === "Nenhuma") return { ...curr, dietary_restrictions: [] };
      if (next.includes(diet)) {
        next = next.filter(d => d !== diet);
      } else {
        next = [...next, diet];
      }
      return { ...curr, dietary_restrictions: next };
    });
  };

  const toggleLang = (lang: string) => {
    setDraft(curr => {
      const next = curr.languages.includes(lang)
        ? curr.languages.filter(l => l !== lang)
        : [...curr.languages, lang];
      return { ...curr, languages: next };
    });
  };

  const canAdvance = useMemo(() => {
    if (step === 0) return Boolean(draft.start_date && draft.end_date && draft.start_date <= draft.end_date);
    if (step === 1) return Boolean(draft.accommodation_name && draft.accommodation_lat);
    if (step === 2) return Boolean(draft.budget);
    if (step === 3) return draft.interests.length > 0;
    return true; // Step 4 always valid
  }, [draft, step]);

  async function handleSubmit() {
    setLoading(true);
    setError(null);
    try {
      const payload = {
        destination: draft.destination,
        origin_city: "",
        currency: draft.currency,
        locale: "pt-BR",
        start_date: draft.start_date,
        end_date: draft.end_date,
        budget: parseFloat(draft.budget),
        style: draft.travel_pace,
        interests: draft.interests.map(i => i.split(" ").slice(1).join(" ") || i),
        accommodation_name: draft.accommodation_name,
        accommodation_address: draft.accommodation_address,
        accommodation_lat: draft.accommodation_lat,
        accommodation_lng: draft.accommodation_lng,
        age_range: draft.age_range,
        traveler_sex: draft.traveler_sex,
        travel_pace: draft.travel_pace,
        dietary_restrictions: draft.dietary_restrictions,
        mobility_notes: draft.mobility_notes,
        languages: draft.languages,
        has_car: draft.has_car,
        daily_start_time: draft.daily_start_time,
        daily_end_time: draft.daily_end_time,
      };

      const trip = await api.createTrip(payload);
      // Wait a tiny bit and go to agent thinking screen (workspace will pick up the running workflow)
      router.push(`/trips/${trip.id}`);
    } catch (err: any) {
      setError(err.message || "Erro ao iniciar a jornada.");
      setLoading(false);
    }
  }

  const stepsInfo = [
    { label: "Datas", title: "Quando voce vai?" },
    { label: "Acomodacao", title: "Onde voce vai ficar?" },
    { label: "Orcamento", title: "Quanto quer gastar?" },
    { label: "Interesses", title: "O que voce ama fazer?" },
    { label: "Perfil", title: "Nos conte sobre voce" }
  ];

  if (loading) {
    return (
      <div className="trip-wizard" style={{ textAlign: "center", padding: "4rem 2rem" }}>
        <h2>Criando seu roteiro...</h2>
        <p style={{ opacity: 0.7, marginTop: "1rem" }}>Preparando tudo para a sua viagem a {draft.destination}.</p>
      </div>
    );
  }

  return (
    <div className="trip-wizard">
      <div className="trip-wizard__header" style={{ marginBottom: "2rem", textAlign: "center" }}>
        <span className="home-logo" style={{ justifyContent: "center", marginBottom: "0.5rem" }}>
          <BrandLogo size={32} />
          <p className="eyebrow" style={{ color: "var(--primary)", margin: 0 }}>BALATravel AI</p>
        </span>
        <h1 style={{ fontSize: "2rem", fontWeight: 700, margin: "0.5rem 0" }}>{stepsInfo[step].title}</h1>
      </div>

      <div className="trip-wizard__steps" style={{ display: "flex", justifyContent: "center", gap: "0.5rem", marginBottom: "2rem" }}>
        {stepsInfo.map((s, idx) => (
          <div key={idx} style={{
            flex: 1, height: "4px", borderRadius: "2px",
            background: idx <= step ? "var(--primary)" : "var(--surface-strong)",
            opacity: idx === step ? 1 : 0.4,
            transition: "all 0.3s"
          }} />
        ))}
      </div>

      <div className="wizard-card" style={{ background: "var(--surface)", padding: "2rem", borderRadius: "1rem", boxShadow: "0 10px 30px rgba(0,0,0,0.05)" }}>
        {/* STEP 0: DATES */}
        {step === 0 && (
          <div className="wizard-step">
            <div className="field-stack" style={{ display: "flex", gap: "1rem" }}>
              <label style={{ flex: 1 }}>
                <span style={{ display: "block", marginBottom: "0.5rem", fontWeight: 600 }}>Data de Chegada</span>
                <input type="date" value={draft.start_date} min={new Date().toISOString().split("T")[0]}
                  onChange={e => setDraft(curr => ({ ...curr, start_date: e.target.value }))}
                  style={{ width: "100%", padding: "0.8rem", borderRadius: "0.5rem", border: "1px solid var(--surface-strong)" }} />
              </label>
              <label style={{ flex: 1 }}>
                <span style={{ display: "block", marginBottom: "0.5rem", fontWeight: 600 }}>Data de Saida</span>
                <input type="date" value={draft.end_date} min={draft.start_date || new Date().toISOString().split("T")[0]}
                  onChange={e => setDraft(curr => ({ ...curr, end_date: e.target.value }))}
                  style={{ width: "100%", padding: "0.8rem", borderRadius: "0.5rem", border: "1px solid var(--surface-strong)" }} />
              </label>
            </div>
            {draft.start_date && draft.end_date && (
               <p style={{ marginTop: "1rem", textAlign: "center", fontSize: "0.9rem", color: "var(--primary)" }}>
                 Sua jornada tera {(new Date(draft.end_date).getTime() - new Date(draft.start_date).getTime()) / (1000 * 3600 * 24)} noites.
               </p>
            )}
          </div>
        )}

        {/* STEP 1: ACCOMMODATION */}
        {step === 1 && (
          <div className="wizard-step">
            <label style={{ display: "block", marginBottom: "1rem" }}>
              <span style={{ display: "block", marginBottom: "0.5rem", fontWeight: 600 }}>Busque seu hotel ou endereco (Google Maps)</span>
              <input ref={autocompleteInputRef} type="text" placeholder="Ex: Copacabana Palace..."
                style={{ width: "100%", padding: "1rem", borderRadius: "0.5rem", border: "1px solid var(--surface-strong)", fontSize: "1.1rem" }} />
            </label>
            {draft.accommodation_name && (
              <div style={{ background: "rgba(0,120,255,0.05)", padding: "1rem", borderRadius: "0.5rem", borderLeft: "4px solid var(--primary)" }}>
                <strong>Confirmado:</strong> {draft.accommodation_name} <br/>
                <span style={{ fontSize: "0.85rem", opacity: 0.8 }}>{draft.accommodation_address}</span>
              </div>
            )}
          </div>
        )}

        {/* STEP 2: BUDGET */}
        {step === 2 && (
          <div className="wizard-step" style={{ textAlign: "center" }}>
            <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: "1rem", fontSize: "2rem", fontWeight: 700 }}>
              <select value={draft.currency} onChange={e => setDraft(c => ({...c, currency: e.target.value}))}
                style={{ fontSize: "1.5rem", border: "none", background: "transparent", cursor: "pointer", fontWeight: 700 }}>
                <option value="BRL">R$</option>
                <option value="USD">$</option>
                <option value="EUR">€</option>
              </select>
              <input type="number" step="100" min="100" value={draft.budget} onChange={e => setDraft(c => ({...c, budget: e.target.value}))}
                style={{ fontSize: "2rem", fontWeight: 700, width: "150px", border: "none", background: "transparent", borderBottom: "2px solid var(--primary)", textAlign: "center" }} />
            </div>
          </div>
        )}

        {/* STEP 3: INTERESTS */}
        {step === 3 && (
          <div className="wizard-step">
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.8rem", justifyContent: "center" }}>
              {INTEREST_OPTIONS.map(interest => {
                const active = draft.interests.includes(interest);
                return (
                  <button key={interest} type="button" onClick={() => toggleInterest(interest)}
                    style={{
                      padding: "0.6rem 1rem", borderRadius: "2rem", border: "1px solid var(--primary)",
                      background: active ? "var(--primary)" : "transparent",
                      color: active ? "white" : "var(--primary)",
                      fontWeight: 600, cursor: "pointer", transition: "all 0.2s"
                    }}>
                    {interest}
                  </button>
                )
              })}
            </div>
          </div>
        )}

        {/* STEP 4: PROFILE */}
        {step === 4 && (
          <div className="wizard-step" style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
            <div style={{ display: "flex", gap: "1rem" }}>
              <label style={{ flex: 1 }}>
                <span style={{ display: "block", marginBottom: "0.5rem", fontWeight: 600 }}>Idade</span>
                <select value={draft.age_range} onChange={e => setDraft(c => ({ ...c, age_range: e.target.value }))}
                  style={{ width: "100%", padding: "0.8rem", borderRadius: "0.5rem", border: "1px solid var(--surface-strong)" }}>
                  <option value="18-25">18 a 25</option>
                  <option value="26-35">26 a 35</option>
                  <option value="36-45">36 a 45</option>
                  <option value="46-60">46 a 60</option>
                  <option value="60+">60+</option>
                </select>
              </label>
              <label style={{ flex: 1 }}>
                <span style={{ display: "block", marginBottom: "0.5rem", fontWeight: 600 }}>Sexo</span>
                <select value={draft.traveler_sex} onChange={e => setDraft(c => ({ ...c, traveler_sex: e.target.value }))}
                  style={{ width: "100%", padding: "0.8rem", borderRadius: "0.5rem", border: "1px solid var(--surface-strong)" }}>
                  <option value="Feminino">Feminino</option>
                  <option value="Masculino">Masculino</option>
                  <option value="Nao-binario">Nao-binario</option>
                  <option value="Nao informar">Prefiro nao dizer</option>
                </select>
              </label>
            </div>

            <div>
              <span style={{ display: "block", marginBottom: "0.8rem", fontWeight: 600 }}>Ritmo de viagem</span>
              <div style={{ display: "flex", gap: "0.5rem" }}>
               {["Leve", "Equilibrado", "Intenso"].map(pace => (
                 <button key={pace} type="button" onClick={() => setDraft(c => ({ ...c, travel_pace: pace }))}
                   style={{ flex: 1, padding: "0.8rem", borderRadius: "0.5rem", border: "1px solid var(--surface-strong)",
                     background: draft.travel_pace === pace ? "var(--primary)" : "transparent",
                     color: draft.travel_pace === pace ? "white" : "inherit", cursor: "pointer", fontWeight: draft.travel_pace === pace ? 600 : 400
                   }}>{pace}</button>
               ))}
              </div>
            </div>

            <div>
              <span style={{ display: "block", marginBottom: "0.8rem", fontWeight: 600 }}>Restricoes Alimentares</span>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
                {DIET_OPTIONS.map(diet => {
                  const isNone = diet === "Nenhuma" && draft.dietary_restrictions.length === 0;
                  const active = isNone || draft.dietary_restrictions.includes(diet);
                  return (
                    <span key={diet} onClick={() => toggleDiet(diet)}
                      style={{ padding: "0.4rem 0.8rem", borderRadius: "0.5rem", cursor: "pointer", fontSize: "0.9rem",
                        background: active ? "var(--primary)" : "var(--surface)", color: active ? "white" : "inherit", border: "1px solid var(--surface-strong)" }}>
                      {diet}
                    </span>
                  );
                })}
              </div>
            </div>
            
            <div>
              <span style={{ display: "block", marginBottom: "0.5rem", fontWeight: 600 }}>Idiomas Falados</span>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
                 {LANG_OPTIONS.map(lang => (
                   <span key={lang} onClick={() => toggleLang(lang)}
                     style={{ padding: "0.4rem 0.8rem", borderRadius: "0.5rem", cursor: "pointer", fontSize: "0.9rem", textTransform: "uppercase",
                       background: draft.languages.includes(lang) ? "var(--surface-strong)" : "transparent", border: "1px solid var(--surface-strong)" }}>
                     {lang}
                   </span>
                 ))}
               </div>
            </div>

            <div style={{ display: "flex", gap: "1rem" }}>
              <label style={{ flex: 2 }}>
                <div style={{ display: "flex", alignItems: "center", gap: "1rem", background: "var(--surface-strong)", padding: "1rem", borderRadius: "12px", border: "1px solid var(--line)" }}>
                  <div style={{ flex: 1 }}>
                    <span style={{ display: "block", fontWeight: 600 }}>Possui carro?</span>
                    <span style={{ fontSize: "0.8rem", opacity: 0.7 }}>O agente considerará trânsito e estacionamento.</span>
                  </div>
                  <input type="checkbox" checked={draft.has_car} onChange={e => setDraft(c => ({ ...c, has_car: e.target.checked }))}
                    style={{ width: "24px", height: "24px", cursor: "pointer" }} />
                </div>
              </label>
              <label style={{ flex: 1 }}>
                <span style={{ display: "block", marginBottom: "0.5rem", fontWeight: 600 }}>Início da Jornada</span>
                <span style={{ fontSize: "0.75rem", opacity: 0.7, display: "block", marginBottom: "0.4rem" }}>Horário sugerido para sair</span>
                <input type="time" value={draft.daily_start_time} onChange={e => setDraft(c => ({...c, daily_start_time: e.target.value}))}
                  style={{ width: "100%", padding: "0.8rem", borderRadius: "0.5rem", border: "1px solid var(--surface-strong)" }} />
              </label>
              <label style={{ flex: 1 }}>
                <span style={{ display: "block", marginBottom: "0.5rem", fontWeight: 600 }}>Fim da Jornada</span>
                <span style={{ fontSize: "0.75rem", opacity: 0.7, display: "block", marginBottom: "0.4rem" }}>Horário sugerido para voltar</span>
                <input type="time" value={draft.daily_end_time} onChange={e => setDraft(c => ({...c, daily_end_time: e.target.value}))}
                  style={{ width: "100%", padding: "0.8rem", borderRadius: "0.5rem", border: "1px solid var(--surface-strong)" }} />
              </label>
            </div>

            <label>
              <span style={{ display: "block", marginBottom: "0.5rem", fontWeight: 600 }}>Restricoes de mobilidade ou obeservacoes</span>
              <textarea placeholder="Opcional. Ex: Viajando com carrinho de bebe, dificuldade com escadas..." value={draft.mobility_notes} onChange={e => setDraft(c => ({...c, mobility_notes: e.target.value}))}
                style={{ width: "100%", padding: "0.8rem", borderRadius: "0.5rem", border: "1px solid var(--surface-strong)", minHeight: "80px" }} />
            </label>
          </div>
        )}

        {error && <p style={{ color: "red", marginTop: "1rem", textAlign: "center" }}>{error}</p>}

        <div style={{ display: "flex", justifyContent: "space-between", marginTop: "2rem", paddingTop: "2rem", borderTop: "1px solid var(--surface-strong)" }}>
          <button type="button" onClick={() => setStep(c => c - 1)} disabled={step === 0}
            style={{ padding: "0.8rem 2rem", borderRadius: "2rem", background: "transparent", border: "none", cursor: step === 0 ? "default" : "pointer", opacity: step === 0 ? 0 : 1 }}>
            Voltar
          </button>
          
          <button type="button" onClick={() => step === 4 ? handleSubmit() : setStep(c => c + 1)} disabled={!canAdvance}
            style={{ padding: "0.8rem 2rem", borderRadius: "2rem", background: canAdvance ? "var(--primary)" : "var(--surface-strong)", color: "white", fontWeight: 600, border: "none", cursor: canAdvance ? "pointer" : "not-allowed" }}>
            {step === 4 ? "Planejar Viagem" : "Continuar"}
          </button>
        </div>
      </div>
    </div>
  );
}
