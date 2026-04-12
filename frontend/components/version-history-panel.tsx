import type { ItineraryVersion } from "@/lib/types";

type Props = {
  versions: ItineraryVersion[];
  busyAction: string | null;
  onRollback: (versionId: number) => Promise<void>;
};

export function VersionHistoryPanel({ versions, busyAction, onRollback }: Props) {
  if (!versions.length) {
    return null;
  }

  return (
    <section className="panel stack-gap">
      <div className="section-header">
        <h2>Versoes do roteiro</h2>
        <span>{versions.length}</span>
      </div>
      <div className="stack-gap">
        {versions
          .slice()
          .sort((left, right) => right.version - left.version)
          .map((version) => (
            <article key={version.id} className="history-entry">
              <div className="history-entry__top">
                <strong>Versao {version.version}</strong>
                <span>{version.status === "active" ? "ativa" : "arquivada"}</span>
              </div>
              <p>{version.assistant_summary || "Sem resumo."}</p>
              {version.status !== "active" ? (
                <button
                  className="button-secondary"
                  disabled={busyAction === `rollback-${version.id}`}
                  onClick={async () => {
                    await onRollback(version.id);
                  }}
                  type="button"
                >
                  {busyAction === `rollback-${version.id}` ? "Restaurando..." : "Restaurar esta versao"}
                </button>
              ) : null}
            </article>
          ))}
      </div>
    </section>
  );
}
