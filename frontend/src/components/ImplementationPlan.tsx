import { Badge } from "@/components/ui/badge";
import type { ImplementationPlan } from "../types";

const STRATEGY_LABEL: Record<string, string> = {
  transplant: "Transplant → fetch",
  upgrade: "Version upgrade",
  shim: "Compatibility shim",
  accept_risk: "Accept risk",
};

export function ImplementationPlanView({ plan }: { plan: ImplementationPlan }) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="primary" className="font-mono">
          {STRATEGY_LABEL[plan.strategy] ?? plan.strategy}
        </Badge>
        <span className="text-[11px] text-muted-foreground">grounded in Cognee code memory</span>
      </div>
      {plan.summary && (
        <p className="text-[13px] leading-relaxed text-foreground">{plan.summary}</p>
      )}
      <ol className="flex flex-col gap-3">
        {plan.steps.map((step, i) => (
          <li key={i} className="rounded-lg border bg-card p-3">
            <div className="flex items-start gap-2.5">
              <span className="grad-brand mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-bold text-white">
                {i + 1}
              </span>
              <div className="min-w-0">
                <h4 className="text-[13px] font-semibold">{step.title}</h4>
                <p className="mt-1 text-[12.5px] leading-relaxed text-muted-foreground">{step.detail}</p>
                {step.file_refs.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {step.file_refs.map((f) => (
                      <code
                        key={f}
                        className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px] text-foreground"
                      >
                        {f}
                      </code>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </li>
        ))}
      </ol>
      {plan.grounded_files.length > 0 && (
        <div>
          <div className="eyebrow mb-1.5">Files this plan touches</div>
          <div className="flex flex-wrap gap-1.5">
            {plan.grounded_files.map((f) => (
              <code
                key={f}
                className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px] text-foreground"
              >
                {f}
              </code>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
