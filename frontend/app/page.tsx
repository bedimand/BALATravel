import Link from "next/link";

export default function HomePage() {
  return (
    <main className="workspace-app">
      <header className="workspace-header" style={{ alignItems: "center", marginBottom: "2rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <div className="map-pin" style={{ width: "2.5rem", height: "2.5rem", boxShadow: "0 0 20px var(--primary-soft)" }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 22s-8-4.5-8-11.8A8 8 0 0 1 12 2a8 8 0 0 1 8 8.2c0 7.3-8 11.8-8 11.8z" />
              <circle cx="12" cy="10" r="3" />
            </svg>
          </div>
          <h1 style={{ fontSize: "1.4rem", letterSpacing: "1px", color: "var(--text)" }}>
            BALA<span style={{ color: "var(--primary)" }}>Travel</span>
          </h1>
        </div>
        <Link href="/history" className="button-ghost" style={{ fontSize: "0.85rem", padding: "0.5rem 1rem" }}>
          Ver trips
        </Link>
      </header>

      <section className="hero-card" style={{ textAlign: "center", alignItems: "center", overflow: "hidden", position: "relative" }}>
        <div style={{ position: "absolute", top: "-50px", left: "-50px", width: "150px", height: "150px", background: "var(--primary-soft)", filter: "blur(40px)", borderRadius: "50%" }}></div>
        <div style={{ position: "absolute", bottom: "-50px", right: "-50px", width: "150px", height: "150px", background: "var(--accent-soft)", filter: "blur(40px)", borderRadius: "50%" }}></div>

        <div className="hero-copy" style={{ position: "relative", zIndex: 10, display: "flex", flexDirection: "column", gap: "1rem", alignItems: "center" }}>
          <span className="stage-pill stage-pill--ready" style={{ display: "inline-flex", gap: "0.5rem", marginBottom: "0.5rem" }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M5 12h14M12 5l7 7-7 7" />
            </svg>
            Seu trip planner com workflow real
          </span>
          <h1 style={{ marginBottom: "0.5rem" }}>Descubra o que fazer. Ajuste o roteiro no caminho.</h1>
          <p className="lede" style={{ maxWidth: "80%", margin: "0 auto" }}>
            Uma experiencia mobile-first para planejar a viagem em torno de lugares, clima, ritmo e mudancas do dia a dia.
          </p>
          <div className="hero-actions" style={{ justifyContent: "center", marginTop: "1rem" }}>
            <Link href="/trips/new" className="button-primary" style={{ padding: "1rem 1.8rem", fontSize: "1.1rem" }}>
              Nova viagem
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M5 12h14M12 5l7 7-7 7" />
              </svg>
            </Link>
            <Link href="/history" className="button-secondary" style={{ padding: "1rem 1.8rem", fontSize: "1.1rem" }}>
              Ver roteiros salvos
            </Link>
          </div>
        </div>
      </section>

      <h3 style={{ marginTop: "2rem", marginBottom: "1rem", paddingLeft: "0.5rem", fontSize: "1.1rem", color: "var(--text)" }}>Por que o BALATravel?</h3>
      <div className="history-grid">
        <article className="preview-column phone-card--accent" style={{ display: "flex", flexDirection: "column", gap: "0.5rem", transform: "none" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", color: "var(--primary)" }}>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 20V10M18 20V4M6 20v-4" />
            </svg>
            <strong style={{ fontSize: "1.1rem", color: "var(--text)" }}>Setup inteligente</strong>
          </div>
          <p className="lede" style={{ fontSize: "0.9rem" }}>Destino, datas, estilo e interesses viram um plano de exploracao em vez de uma fila de reservas.</p>
        </article>

        <article className="preview-column" style={{ display: "flex", flexDirection: "column", gap: "0.5rem", transform: "none" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", color: "var(--accent)" }}>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <path d="M12 16v-4" />
              <path d="M12 8h.01" />
            </svg>
            <strong style={{ fontSize: "1.1rem", color: "var(--text)" }}>Curadoria dinamica</strong>
          </div>
          <p className="lede" style={{ fontSize: "0.9rem" }}>Lugares, bairros e experiencias aparecem em uma curadoria clara, com mapa, clima e carga de deslocamento.</p>
        </article>

        <article className="preview-column" style={{ display: "flex", flexDirection: "column", gap: "0.5rem", transform: "none" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", color: "var(--warning)" }}>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
              <path d="M3 3v5h5" />
            </svg>
            <strong style={{ fontSize: "1.1rem", color: "var(--text)" }}>Atualizacao constante</strong>
          </div>
          <p className="lede" style={{ fontSize: "0.9rem" }}>Comecou a chover ou o dia ficou cansativo? O agente reorganiza o roteiro e deixa a mudanca pronta para aprovar.</p>
        </article>
      </div>

      <div style={{ height: "4rem" }}></div>
    </main>
  );
}
