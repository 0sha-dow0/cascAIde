import { useEffect, useState } from "react";
import { api, ApiError, type DiscussKind } from "./api";
import { showToast } from "./toast";
import { DiffReview } from "./components/DiffReview";
import { GraphPanel } from "./components/GraphPanel";
import { ImplementationPlanView } from "./components/ImplementationPlan";
import { AccountMenu } from "./components/AccountMenu";
import type { AppConfig, Session } from "./session";
import { ThemeToggle } from "./components/theme-toggle";
import { usePipelineStream } from "./usePipelineStream";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Arrow, Check, Search, Spinner } from "@/components/icons";
import type {
  ImplementationPlan, MitigationOption, PipelineEvent, RegisterRepoResponse, StrategyKind,
  Transplant, UnderwritingReport,
} from "./types";

const STAGES = ["recall", "rewrite", "validate", "verify_build", "verify_test", "verify_behavioral", "judge"];
const STAGE_LABEL: Record<string, string> = {
  recall: "Recall recipe",
  rewrite: "Rewrite call sites",
  validate: "Validate (node --check)",
  verify_build: "Build",
  verify_test: "Test suite",
  verify_behavioral: "Behavioral diff",
  judge: "Judge panel",
  awaiting_review: "Awaiting review",
  completed: "Completed",
  contested: "Contested",
  failed: "Failed",
  rejected: "Rejected",
};

export default function App({
  config = null,
  session = null,
  onSignOut,
}: {
  config?: AppConfig | null;
  session?: Session | null;
  onSignOut?: () => void;
} = {}) {
  const [url, setUrl] = useState("https://github.com/0sha-dow0/test-hackbybay3.0");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [scan, setScan] = useState<RegisterRepoResponse | null>(null);
  const [repoId, setRepoId] = useState<string | null>(null);
  const [options, setOptions] = useState<MitigationOption[] | null>(null);
  const [incidentId, setIncidentId] = useState<string | null>(null);
  const [transplant, setTransplant] = useState<Transplant | null>(null);
  const [plan, setPlan] = useState<ImplementationPlan | null>(null);
  const [exploring, setExploring] = useState<StrategyKind | null>(null);
  const [discussing, setDiscussing] = useState<DiscussKind | null>(null);
  const [running, setRunning] = useState<StrategyKind | null>(null);
  const { events, terminalStage } = usePipelineStream(incidentId);

  const pollForTransplant = async (id: string) => {
    for (let i = 0; i < 40; i++) {
      try {
        const t = await api.getTransplant(`transplant-${id}`);
        setTransplant(t);
        setStatus(
          t.consensus.verdicts.length === 0
            ? "Review ready — patch ready to open a PR"
            : t.consensus.approved
              ? "Review ready — judges approved"
              : "Review ready — contested",
        );
        return;
      } catch {
        await new Promise((r) => setTimeout(r, 1500));
      }
    }
    setStatus("Transplant did not complete — try again");
  };
  useEffect(() => {
    if (terminalStage) setStatus(`Pipeline ${terminalStage}`);
  }, [terminalStage]);

  const openDiscussion = async (kind: DiscussKind) => {
    if (!incidentId || discussing) return;
    setDiscussing(kind);
    const label = kind === "issue" ? "issue" : "discussion";
    setStatus(`Opening a ${label} on GitHub…`);
    try {
      const r = await api.discuss(incidentId, kind);
      if (kind === "issue") {
        showToast(`Issue #${r.number} opened on GitHub`, "success", "Issue opened");
      } else {
        showToast("Opening the discussion form on GitHub — review and post it.", "info", "Discussion");
      }
      setStatus(`Opened a ${label} on GitHub`);
      window.open(r.url, "_blank", "noreferrer");
    } catch (e) {
      handlePermissionError(e, `Couldn't open the ${label}`);
    } finally {
      setDiscussing(null);
    }
  };

  const handlePermissionError = (e: unknown, fallback: string) => {
    const err = e as ApiError;
    if (err?.status === 403) {
      showToast(err.message, "denied", "You don't have permission");
      setStatus("Access denied — check your GitHub permission on this repo");
    } else if (err?.status === 409) {
      showToast(err.message, "warning", "Connect GitHub");
      setStatus("Connect GitHub to continue");
    } else {
      setStatus(`${fallback}: ${(e as Error).message}`);
    }
  };

  const doScan = async () => {
    setBusy(true);
    setStatus("Cloning + scanning (public repos are git-cloned live)…");
    setScan(null); setOptions(null); setTransplant(null); setIncidentId(null); setPlan(null);
    try {
      const d = await api.registerRepo(url.trim());
      setScan(d); setRepoId(d.repo.id); setStatus("Scanned — graph built in Neo4j");
    } catch (e) {
      setStatus(`Scan failed: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  };
  const doFire = async () => {
    if (!repoId) return;
    setStatus("Firing CVE incident…");
    try {
      const d = await api.fireIncident(repoId);
      setIncidentId(d.incident.id); setOptions(d.options.options); setStatus("Incident open — choose a strategy");
    } catch (e) {
      handlePermissionError(e, "Couldn't fire the CVE");
    }
  };
  const runTransplant = async (kind: StrategyKind) => {
    if (!incidentId || running) return; // guard: one pipeline run at a time
    setRunning(kind);
    setTransplant(null);
    setStatus("Pipeline running (live transplant + 4 judges)…");
    showToast(
      "Running the transplant and 4-judge review — this takes ~30–60s. No need to click again.",
      "info",
      "Pipeline started",
    );
    try {
      await api.chooseStrategy(incidentId, kind);
      await pollForTransplant(incidentId);
    } catch (e) {
      setStatus(`Pipeline failed: ${(e as Error).message}`);
    } finally {
      setRunning(null);
    }
  };
  const explore = async (kind: StrategyKind) => {
    if (!incidentId) return;
    setExploring(kind);
    setStatus("Exploring implementation — indexing code into Cognee + planning with Groq…");
    try {
      const p = await api.explore(incidentId, kind);
      setPlan(p);
      setStatus("Implementation plan ready");
    } catch (e) {
      setStatus(`Explore failed: ${(e as Error).message}`);
    } finally {
      setExploring(null);
    }
  };

  return (
    <div className="min-h-screen pt-14">
      <header className="fixed inset-x-0 top-0 z-40 border-b bg-background">
        <div className="mx-auto flex h-14 max-w-[1240px] items-center gap-3 px-6">
          <a href="#" className="flex items-center gap-2.5" title="Back to home">
            <span className="grad-brand flex h-7 w-7 items-center justify-center rounded-[8px] text-[15px] font-bold text-white shadow-sm">
              ⟩
            </span>
            <span className="grad-text font-display text-[16px] font-bold tracking-tight">cascAIde</span>
          </a>
          <div className="mx-2 hidden h-5 sm:block">
            <div className="h-full w-px bg-border" />
          </div>
          <Input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="Public GitHub repo URL"
            className="max-w-xl flex-1 font-mono text-[13px]"
            onKeyDown={(e) => { if (e.key === "Enter") void doScan(); }}
          />
          <Button onClick={doScan} disabled={busy}>
            {busy ? <Spinner /> : <Search />}
            Scan repo
          </Button>
          <Button variant="outline" onClick={doFire} disabled={!repoId}>
            Fire CVE
          </Button>
          <ThemeToggle />
          {config?.auth_required && session && onSignOut && (
            <AccountMenu config={config} session={session} onSignOut={onSignOut} />
          )}
        </div>
      </header>

      <main className="mx-auto flex max-w-[1240px] flex-col gap-6 px-6 py-7">
        <div className="flex items-end justify-between gap-4">
          <div>
            <h1 className="font-display text-xl font-semibold tracking-tight">
              Autonomous dependency transplant
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Map the blast radius, rewrite <span className="font-mono text-[13px]">axios → fetch</span>, prove behavior, gate on a 4-judge consensus + you.
            </p>
          </div>
          {status && (
            <span className="hidden shrink-0 items-center gap-2 rounded-full border bg-card px-3 py-1.5 text-[12.5px] text-muted-foreground md:inline-flex">
              {busy && <Spinner className="size-3.5" />}
              {status}
            </span>
          )}
        </div>

        <Card className="animate-fade-rise">
          <CardHeader>
            <CardTitle>Dependency &amp; call-site graph</CardTitle>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="destructive">vulnerable dep</Badge>
              <Badge variant="outline">file</Badge>
              <Badge variant="warning">aliased call site</Badge>
              <Badge variant="outline">call site</Badge>
            </div>
          </CardHeader>
          <CardContent className="h-[440px] p-0">
            <GraphPanel
              layout={scan?.graph_layout ?? null}
              plan={scan?.surgery_plan ?? null}
              underwriting={scan?.underwriting ?? null}
            />
          </CardContent>
        </Card>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div className="flex flex-col gap-6">
            <Panel title="What's vulnerable · how it changes" delay={60}>
              {scan ? <VulnBody scan={scan} onAssess={doFire} hasOptions={!!options} /> : <Empty>Scan a repo to see the flagged dependency.</Empty>}
            </Panel>
            <Panel title="Underwriting · blast radius" delay={110}>
              {scan ? (
                <UnderBody u={scan.underwriting} aliased={scan.surgery_plan.call_sites.filter((c) => c.is_aliased).length} />
              ) : (
                <Empty>Kill-test evidence appears after a scan.</Empty>
              )}
            </Panel>
            <Panel title="Mitigation strategies" delay={160}>
              {options ? (
                <Mitigation
                  options={options}
                  onRun={runTransplant}
                  onExplore={explore}
                  exploring={exploring}
                  onDiscuss={openDiscussion}
                  discussing={discussing}
                  running={running}
                />
              ) : (
                <Empty>Fire a CVE to see ranked strategies.</Empty>
              )}
            </Panel>
            <Panel title="Live pipeline" delay={210}>
              {incidentId ? <PipelineRail events={events} terminalStage={terminalStage} /> : <Empty>The transplant pipeline streams here.</Empty>}
            </Panel>
          </div>

          <div className="flex flex-col gap-6 lg:sticky lg:top-20 lg:self-start">
            {plan && (
              <Panel title="Implementation plan" delay={90}>
                <ImplementationPlanView plan={plan} />
                <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t pt-4">
                  <span className="text-[12.5px] text-muted-foreground">
                    Take this plan to the team on GitHub
                  </span>
                  <DiscussButtons onDiscuss={openDiscussion} discussing={discussing} />
                </div>
              </Panel>
            )}
            <Panel title="Diff review · judge verdicts" delay={110}>
              {transplant ? <DiffReview transplant={transplant} /> : <Empty>Run a transplant to review the diff and judge verdicts.</Empty>}
            </Panel>
          </div>
        </div>
      </main>
    </div>
  );
}

function Panel({ title, delay, children }: { title: string; delay?: number; children: React.ReactNode }) {
  return (
    <Card className="animate-fade-rise" style={delay ? { animationDelay: `${delay}ms` } : undefined}>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="text-sm text-muted-foreground">{children}</p>;
}

type BadgeVariant = "default" | "outline" | "primary" | "success" | "destructive" | "warning";

function severityVariant(severity: string): BadgeVariant {
  switch (severity.toLowerCase()) {
    case "critical":
      return "destructive";
    case "high":
      return "warning";
    case "medium":
    case "moderate":
      return "default";
    default:
      return "outline";
  }
}

function SeverityBadge({ severity }: { severity: string }) {
  return <Badge variant={severityVariant(severity)}>{severity.toUpperCase()}</Badge>;
}

function VulnBody({
  scan,
  onAssess,
  hasOptions,
}: {
  scan: RegisterRepoResponse;
  onAssess: () => void;
  hasOptions: boolean;
}) {
  const p = scan.surgery_plan;
  const advisories = scan.underwriting.advisories;
  const label = `${p.target_package}${p.target_version ? `@${p.target_version}` : ""}`;
  return (
    <div className="flex flex-col gap-3.5">
      <p className="text-sm">
        <Badge variant="destructive" className="mr-1.5 align-middle font-mono">{label}</Badge>
        is the flagged dependency — {p.affected_files.length} file{p.affected_files.length === 1 ? "" : "s"}, {p.call_sites.length} call site{p.call_sites.length === 1 ? "" : "s"}.
      </p>
      {advisories.length > 0 ? (
        <div className="flex flex-col gap-2">
          <div className="eyebrow">Known advisories · GitHub Advisory Database</div>
          {advisories.map((a) => (
            <div key={a.ghsa_id} className="rounded-md border bg-card p-3">
              <div className="flex items-center justify-between gap-2">
                <a
                  href={a.url}
                  target="_blank"
                  rel="noreferrer"
                  className="font-mono text-[12.5px] font-medium text-primary hover:underline"
                >
                  {a.cve_id ?? a.ghsa_id}
                </a>
                <div className="flex items-center gap-2">
                  <span className="tnums text-[11.5px] text-muted-foreground">CVSS {a.cvss_score.toFixed(1)}</span>
                  <SeverityBadge severity={a.severity} />
                </div>
              </div>
              <p className="mt-1.5 text-[12.5px] leading-relaxed text-muted-foreground">{a.summary}</p>
              <div className="mt-1.5 text-[11px] text-muted-foreground">
                affects <span className="font-mono">{a.vulnerable_range || "—"}</span>
                {a.first_patched && (
                  <>
                    {" · "}fixed in <span className="font-mono text-foreground">{a.first_patched}</span>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-[13px] leading-relaxed text-muted-foreground">
          No published advisory matched <span className="font-mono text-foreground">{label}</span> — but axios{" "}
          <span className="text-foreground">throws on non-2xx</span> where a native fetch does not, so the transplant still
          closes that behavioral gap.
        </p>
      )}
      <p className="text-[13px] leading-relaxed text-muted-foreground">
        Each call site is rewritten to a native <span className="font-mono text-[12.5px]">fetch</span> wrapper that throws on
        non-2xx and parses JSON, so behavior is preserved and the vulnerable package is removed.
      </p>
      <Button onClick={onAssess} className="w-full" variant={hasOptions ? "outline" : "default"}>
        {hasOptions ? "Strategies ready — choose one below" : "Assess mitigation strategies"}
        <Arrow />
      </Button>
      <div>
        <div className="eyebrow mb-2">Call sites · surgery plan</div>
        <div className="flex flex-col gap-1.5">
          {p.call_sites.map((c, i) => (
            <div
              key={i}
              className={`rounded-md border-l-2 bg-muted/40 px-3 py-2 text-[12.5px] ${c.is_aliased ? "border-l-warning" : "border-l-border"}`}
            >
              <span className="font-mono font-medium">{c.file_path}</span>
              <span className="text-muted-foreground">:{c.line} · </span>
              <span className="font-mono">{c.symbol}</span>
              {c.is_aliased && (
                <Badge variant="warning" className="ml-2 align-middle">
                  aliased → {c.alias} · grep misses this
                </Badge>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Stat({ value, label }: { value: string | number; label: string }) {
  return (
    <div className="rounded-md border bg-muted/30 px-3 py-2.5">
      <div className="tnums font-display text-2xl font-semibold leading-none">{value}</div>
      <div className="mt-1.5 text-[11px] text-muted-foreground">{label}</div>
    </div>
  );
}

function priorityTint(band: string): string {
  switch (band) {
    case "critical":
      return "border-destructive/30 bg-destructive/[0.06]";
    case "high":
      return "border-warning/30 bg-warning/[0.06]";
    case "medium":
      return "border-primary/25 bg-primary/[0.05]";
    default:
      return "";
  }
}

function UnderBody({ u, aliased }: { u: UnderwritingReport; aliased: number }) {
  return (
    <div className="flex flex-col gap-3.5">
      <div className={`flex items-center justify-between rounded-md border p-3 ${priorityTint(u.priority_band)}`}>
        <div>
          <div className="eyebrow">CVE priority</div>
          <div className="text-[11.5px] text-muted-foreground">severity × blast surface</div>
        </div>
        <div className="flex items-center gap-3">
          <span className="tnums font-display text-3xl font-semibold leading-none">
            {u.priority_score.toFixed(0)}
          </span>
          <SeverityBadge severity={u.priority_band} />
        </div>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <Stat value={u.affected_file_count} label="affected files" />
        <Stat value={u.failing_tests.length} label="failing tests" />
        <Stat value={(u.centrality[0]?.score ?? 0).toFixed(2)} label="axios centrality" />
      </div>
      {u.failing_tests.length > 0 ? (
        <ul className="flex flex-col gap-1">
          {u.failing_tests.map((t) => (
            <li key={t} className="font-mono text-[12.5px] text-destructive">{t}</li>
          ))}
        </ul>
      ) : (
        <p className="text-[13px] leading-relaxed text-muted-foreground">
          The graph proves {u.affected_file_count} file{u.affected_file_count === 1 ? "" : "s"} touch the target
          {aliased ? `, including ${aliased} aliased site${aliased === 1 ? "" : "s"} a grep would miss` : ""}.
        </p>
      )}
      {u.warnings.length > 0 && (
        <Alert variant="warning" className="text-[12.5px]">
          {u.warnings.map((w) => w.shape).join(", ")}
        </Alert>
      )}
    </div>
  );
}

function DiscussButtons({
  onDiscuss,
  discussing,
}: {
  onDiscuss: (k: DiscussKind) => void;
  discussing: DiscussKind | null;
}) {
  return (
    <div className="flex items-center gap-2">
      <Button
        size="sm"
        variant="outline"
        disabled={discussing !== null}
        onClick={() => onDiscuss("issue")}
      >
        {discussing === "issue" ? (
          <>
            <Spinner /> Opening…
          </>
        ) : (
          "Open issue"
        )}
      </Button>
      <Button
        size="sm"
        variant="outline"
        disabled={discussing !== null}
        onClick={() => onDiscuss("discussion")}
      >
        {discussing === "discussion" ? (
          <>
            <Spinner /> Opening…
          </>
        ) : (
          "Start discussion"
        )}
      </Button>
    </div>
  );
}

function Mitigation({
  options,
  onRun,
  onExplore,
  exploring,
  onDiscuss,
  discussing,
  running,
}: {
  options: MitigationOption[];
  onRun: (k: StrategyKind) => void;
  onExplore: (k: StrategyKind) => void;
  exploring: StrategyKind | null;
  onDiscuss: (k: DiscussKind) => void;
  discussing: DiscussKind | null;
  running: StrategyKind | null;
}) {
  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-dashed bg-muted/30 px-3.5 py-2.5">
        <span className="text-[12.5px] text-muted-foreground">
          Want the team's take before you fix it?
        </span>
        <DiscussButtons onDiscuss={onDiscuss} discussing={discussing} />
      </div>
      {options.map((o) => (
        <div
          key={o.kind}
          className={`rounded-lg border p-3.5 ${o.executable ? "border-primary/40 bg-primary/[0.04]" : "bg-card"}`}
        >
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-[14px] font-semibold">{o.title}</h3>
            <Badge variant={o.executable ? "primary" : "outline"}>
              {o.executable ? "executed end-to-end" : "roadmap"}
            </Badge>
          </div>
          <div className="mt-1 text-[11.5px] text-muted-foreground">
            effort {o.effort} · blast {o.blast_radius} · residual {o.residual_risk}
          </div>
          <p className="mt-1.5 text-[12.5px] leading-relaxed text-muted-foreground">{o.rationale}</p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {o.executable && (
              <Button size="sm" disabled={running !== null} onClick={() => onRun(o.kind)}>
                {running === o.kind ? (
                  <>
                    <Spinner /> Running…
                  </>
                ) : o.kind === "upgrade" ? (
                  "Apply upgrade"
                ) : (
                  "Run transplant"
                )}
              </Button>
            )}
            <Button
              size="sm"
              variant="outline"
              disabled={exploring !== null}
              onClick={() => onExplore(o.kind)}
            >
              {exploring === o.kind ? (
                <>
                  <Spinner className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                  Exploring…
                </>
              ) : (
                "Explore how"
              )}
            </Button>
          </div>
        </div>
      ))}
    </div>
  );
}

function PipelineRail({ events, terminalStage }: { events: PipelineEvent[]; terminalStage: string | null }) {
  const last = events[events.length - 1];
  const activeStage = last && !last.terminal ? last.stage : null;
  const rows: { key: string; label: string; msg?: string; state: "pending" | "active" | "done"; tone?: string }[] =
    STAGES.map((s) => {
      const e = events.find((ev) => ev.stage === s);
      const state = !e ? "pending" : s === activeStage ? "active" : "done";
      return { key: s, label: STAGE_LABEL[s] ?? s, msg: e?.message, state };
    });
  if (terminalStage && !STAGES.includes(terminalStage)) {
    const tone =
      terminalStage === "completed" || terminalStage === "awaiting_review" ? "success"
      : terminalStage === "contested" ? "warning" : "destructive";
    const te = events.find((ev) => ev.stage === terminalStage);
    rows.push({ key: terminalStage, label: STAGE_LABEL[terminalStage] ?? terminalStage, msg: te?.message, state: "done", tone });
  }

  return (
    <div className="flex flex-col">
      {rows.map((r, i) => (
        <div key={r.key} className="flex gap-3">
          <div className="flex flex-col items-center">
            <StageNode state={r.state} tone={r.tone} />
            {i < rows.length - 1 && <div className="w-px flex-1 bg-border" style={{ minHeight: 14 }} />}
          </div>
          <div className={`pb-3 ${r.state === "pending" ? "opacity-55" : ""}`}>
            <div className="font-mono text-[12.5px] font-medium leading-4">{r.label}</div>
            {r.msg && r.state !== "pending" && (
              <div className="mt-0.5 text-[11.5px] leading-snug text-muted-foreground">{r.msg}</div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function StageNode({ state, tone }: { state: "pending" | "active" | "done"; tone?: string }) {
  if (state === "active") {
    return (
      <span className="relative mt-0.5 flex h-4 w-4 items-center justify-center">
        <span className="absolute inline-flex h-full w-full rounded-full bg-primary/40 motion-safe:animate-ping" />
        <Spinner className="size-3.5 text-primary" />
      </span>
    );
  }
  if (state === "done") {
    const bg = tone === "warning" ? "bg-warning" : tone === "destructive" ? "bg-destructive" : "bg-success";
    return (
      <span className={`mt-0.5 flex h-4 w-4 items-center justify-center rounded-full text-white ${bg}`}>
        <Check className="size-2.5" />
      </span>
    );
  }
  return <span className="mt-1 h-2.5 w-2.5 rounded-full bg-muted-foreground/30" />;
}
