// Shared styles for the export view and the public share page. Kept as a plain
// string injected via <style> so the document renders identically on a public
// page (no auth, no app shell) and prints to a clean, light-on-white PDF.
export const exportDocStyles = `
  .export-page {
    min-height: 100vh;
    background: #f3f4f6;
    color: #111827;
    padding: 2rem 1rem 4rem;
    font-family: var(--font-body, "Inter", system-ui, sans-serif);
  }
  .export-loading {
    text-align: center;
    opacity: 0.6;
    margin-top: 4rem;
    font-size: 0.95rem;
  }
  .export-toolbar {
    max-width: 720px;
    margin: 0 auto 1rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    flex-wrap: wrap;
  }
  .export-toolbar__actions { display: flex; gap: 0.6rem; flex-wrap: wrap; }
  .export-back {
    color: #2563eb;
    text-decoration: none;
    font-weight: 600;
    font-size: 0.9rem;
  }
  .export-back:hover { text-decoration: underline; }
  .export-btn {
    border: none;
    border-radius: 0.7rem;
    padding: 0.6rem 1.05rem;
    font-size: 0.86rem;
    font-weight: 600;
    cursor: pointer;
    transition: transform 0.15s ease, background 0.15s ease;
  }
  .export-btn:disabled { opacity: 0.6; cursor: default; }
  .export-btn--primary { background: #00b8cc; color: #fff; }
  .export-btn--primary:hover:not(:disabled) { background: #00a3b5; }
  .export-btn--ghost { background: #fff; color: #374151; border: 1px solid #d1d5db; }
  .export-btn--ghost:hover { background: #f9fafb; }
  .export-sharebar {
    max-width: 720px;
    margin: 0 auto 1rem;
    background: #ecfeff;
    border: 1px solid #a5f3fc;
    border-radius: 0.7rem;
    padding: 0.7rem 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
  }
  .export-sharebar__label { font-size: 0.72rem; color: #0e7490; font-weight: 600; }
  .export-sharebar__url { font-size: 0.85rem; color: #155e75; word-break: break-all; }
  .export-inline-error {
    max-width: 720px; margin: 0 auto 1rem; color: #b91c1c; font-size: 0.85rem;
  }
  .export-accom {
    max-width: 720px; margin: 0 auto 0.75rem; font-size: 0.9rem; color: #374151;
  }

  .export-doc {
    max-width: 720px;
    margin: 0 auto;
    background: #fff;
    border-radius: 1rem;
    box-shadow: 0 10px 30px -12px rgba(0,0,0,0.18);
    padding: 2.5rem 2.25rem;
  }
  .export-doc__head {
    border-bottom: 2px solid #111827;
    padding-bottom: 1.1rem;
    margin-bottom: 1.75rem;
  }
  .export-doc__brand {
    margin: 0;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.72rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: #00a3b5;
    font-weight: 800;
  }
  .export-doc__brand-icon {
    width: 1.6rem;
    height: 1.6rem;
    object-fit: contain;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }
  .export-doc__head h1 { margin: 0.35rem 0 0.25rem; font-size: 1.9rem; font-weight: 800; }
  .export-doc__dates { margin: 0; color: #6b7280; font-size: 0.95rem; }
  .export-doc__empty { color: #6b7280; font-size: 0.95rem; }

  .export-day { margin-bottom: 2rem; }
  .export-day__head {
    display: flex; align-items: baseline; gap: 0.6rem; margin-bottom: 0.9rem;
  }
  .export-day__num { font-size: 1.05rem; font-weight: 800; }
  .export-day__date { font-size: 0.82rem; color: #9ca3af; }
  .export-day__count { margin-left: auto; font-size: 0.78rem; color: #9ca3af; }
  .export-day__list { list-style: none; margin: 0; padding: 0; }

  .export-stop {
    display: grid;
    grid-template-columns: 52px 56px 1fr;
    gap: 0.85rem;
    padding: 0.9rem 0;
    border-top: 1px solid #f0f1f3;
    page-break-inside: avoid;
  }
  .export-stop__time {
    font-variant-numeric: tabular-nums;
    font-weight: 700;
    color: #00a3b5;
    font-size: 0.9rem;
    padding-top: 0.15rem;
  }
  .export-stop__thumb {
    width: 56px; height: 56px; border-radius: 0.6rem; overflow: hidden;
    background: #f3f4f6; display: grid; place-items: center; font-size: 1.4rem;
  }
  .export-stop__thumb img { width: 100%; height: 100%; object-fit: cover; }
  .export-stop__body { min-width: 0; }
  .export-stop__title-row { display: flex; align-items: baseline; gap: 0.6rem; }
  .export-stop__title-row h3 { margin: 0; font-size: 1rem; font-weight: 700; }
  .export-stop__rating { color: #d97706; font-size: 0.8rem; font-weight: 700; white-space: nowrap; }
  .export-stop__kind {
    margin: 0.1rem 0 0; font-size: 0.68rem; text-transform: uppercase;
    letter-spacing: 0.06em; color: #9ca3af; font-weight: 600;
  }
  .export-stop__addr { margin: 0.35rem 0 0; font-size: 0.8rem; color: #6b7280; }
  .export-stop__note { margin: 0.4rem 0 0; font-size: 0.83rem; line-height: 1.5; color: #374151; }
  .export-stop__links { margin-top: 0.55rem; display: flex; gap: 0.85rem; flex-wrap: wrap; }
  .export-stop__links a {
    font-size: 0.8rem; font-weight: 600; color: #2563eb; text-decoration: none;
  }
  .export-stop__links a:hover { text-decoration: underline; }

  @media print {
    .export-toolbar, .export-sharebar, .export-inline-error, .export-back { display: none !important; }
    .export-page { background: #fff; padding: 0; }
    .export-doc { box-shadow: none; border-radius: 0; max-width: none; padding: 0.5rem 0; }
    .export-stop__links a { color: #111827; }
  }

  @media (max-width: 600px) {
    .export-doc { padding: 1.5rem 1.1rem; }
    .export-stop { grid-template-columns: 44px 1fr; }
    .export-stop__thumb { display: none; }
  }
`;
