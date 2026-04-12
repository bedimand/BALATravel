type FlowStep = {
  id: string;
  title: string;
  description: string;
  status: "done" | "current" | "pending";
};

type Props = {
  steps: FlowStep[];
  currentStepTitle: string;
  onSearch: () => Promise<void>;
  onGenerate: () => Promise<void>;
  canSearch: boolean;
  canGenerate: boolean;
  busyAction: string | null;
};

export function PlannerFlow({ steps, currentStepTitle, onSearch, onGenerate, canSearch, canGenerate, busyAction }: Props) {
  return (
    <section className="panel planner-flow">
      <div className="planner-flow__header">
        <div>
          <p className="eyebrow">Flow</p>
          <h2>Jornada guiada</h2>
        </div>
        <div className="planner-flow__actions">
          <button className="button-secondary" onClick={onSearch} disabled={!canSearch || busyAction !== null} type="button">
            {busyAction === "search" ? "Buscando..." : "Atualizar opcoes"}
          </button>
          <button className="button-primary" onClick={onGenerate} disabled={!canGenerate || busyAction !== null} type="button">
            {busyAction === "generate" ? "Gerando..." : "Gerar roteiro"}
          </button>
        </div>
      </div>
      <p className="planner-flow__lede">
        O agente prepara contexto e compara alternativas, mas a decisao de voo e hospedagem continua com voce.
      </p>
      <div className="planner-flow__grid">
        {steps.map((step, index) => (
          <article key={step.id} className={`flow-step flow-step--${step.status}`}>
            <span className="flow-step__index">0{index + 1}</span>
            <div className="flow-step__copy">
              <strong>{step.title}</strong>
              <p>{step.description}</p>
            </div>
            <span className="flow-step__status">
              {step.status === "done" ? "Concluida" : step.status === "current" ? "Atual" : "Aguardando"}
            </span>
          </article>
        ))}
      </div>
      <div className="planner-flow__footer">
        <span>Etapa atual</span>
        <strong>{currentStepTitle}</strong>
      </div>
    </section>
  );
}
