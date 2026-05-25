import Link from "next/link";

export default function HomePage() {
  return (
    <main className="workspace-app">
      <header className="home-header">
        <div className="home-logo">
          <div className="map-pin">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 22s-8-4.5-8-11.8A8 8 0 0 1 12 2a8 8 0 0 1 8 8.2c0 7.3-8 11.8-8 11.8z" />
              <circle cx="12" cy="10" r="3" />
            </svg>
          </div>
          <h1>BALA<span>Travel</span></h1>
        </div>
        <Link href="/history" className="button-ghost">
          Ver trips
        </Link>
      </header>

      <section className="hero-card hero-section">
        <div className="hero-blur hero-blur--left"></div>
        <div className="hero-blur hero-blur--right"></div>

        <div className="hero-content hero-copy">
          <span className="stage-pill stage-pill--ready">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M5 12h14M12 5l7 7-7 7" />
            </svg>
            Seu trip planner com workflow real
          </span>
          <h1>Descubra o que fazer. Ajuste o roteiro no caminho.</h1>
          <p className="lede">
            Uma experiencia mobile-first para planejar a viagem em torno de lugares, clima, ritmo e mudancas do dia a dia.
          </p>
          <div className="hero-actions">
            <Link href="/trips/new" className="button-primary button-large">
              Nova viagem
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M5 12h14M12 5l7 7-7 7" />
              </svg>
            </Link>
            <Link href="/history" className="button-secondary button-large">
              Ver roteiros salvos
            </Link>
          </div>
        </div>
      </section>

      <h3 className="features-heading">Por que o BALATravel?</h3>
      <div className="history-grid">
        <article className="preview-column phone-card--accent feature-card">
          <div className="feature-icon feature-icon--primary">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 20V10M18 20V4M6 20v-4" />
            </svg>
            <strong>Setup inteligente</strong>
          </div>
          <p className="lede">Destino, datas, estilo e interesses viram um plano de exploracao em vez de uma fila de reservas.</p>
        </article>

        <article className="preview-column feature-card">
          <div className="feature-icon feature-icon--accent">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <path d="M12 16v-4" />
              <path d="M12 8h.01" />
            </svg>
            <strong>Curadoria dinamica</strong>
          </div>
          <p className="lede">Lugares, bairros e experiencias aparecem em uma curadoria clara, com mapa, clima e carga de deslocamento.</p>
        </article>

        <article className="preview-column feature-card">
          <div className="feature-icon feature-icon--warning">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
              <path d="M3 3v5h5" />
            </svg>
            <strong>Atualizacao constante</strong>
          </div>
          <p className="lede">Comecou a chover ou o dia ficou cansativo? O agente reorganiza o roteiro e deixa a mudanca pronta para aprovar.</p>
        </article>
      </div>

      <div style={{ height: "4rem" }}></div>
    </main>
  );
}
