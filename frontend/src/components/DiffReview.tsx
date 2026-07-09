import { useMemo, useState } from "react";
import { api, ApiError } from "../api";
import { showToast } from "../toast";
import type { Transplant } from "../types";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Arrow, Check, Spinner, Warn } from "@/components/icons";

interface ReviewResult {
  ok: boolean;
  message: string;
  url?: string;
  number?: number;
}

function lineClass(line: string): string {
  if (line.startsWith("+") && !line.startsWith("+++")) return "diff-add";
  if (line.startsWith("-") && !line.startsWith("---")) return "diff-del";
  if (line.startsWith("@@") || line.startsWith("---") || line.startsWith("+++")) return "diff-hd";
  return "";
}

export function DiffReview({ transplant }: { transplant: Transplant }) {
  const c = transplant.consensus;
  const [rejected, setRejected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState<"accept" | "reject" | null>(null);
  const [result, setResult] = useState<ReviewResult | null>(null);
  const anyReject = rejected.size > 0;

  const toggle = (path: string, isReject: boolean) =>
    setRejected((prev) => {
      const next = new Set(prev);
      if (isReject) next.add(path);
      else next.delete(path);
      return next;
    });

  const handleError = (e: unknown) => {
    const err = e as ApiError;
    if (err?.status === 403) {
      showToast(err.message, "denied", "You don't have permission");
      setResult({ ok: false, message: err.message });
    } else if (err?.status === 409) {
      showToast(err.message, "warning", "Connect GitHub");
      setResult({ ok: false, message: err.message });
    } else {
      setResult({ ok: false, message: (e as Error).message });
    }
  };

  const accept = async () => {
    if (busy) return;
    setBusy("accept");
    setResult(null);
    try {
      const perFile = transplant.diff.map((f) => ({ path: f.path, kind: "accept" as const, reason: null }));
      const r = await api.submitReview(transplant.id, "accept_all", perFile, null);
      if (r.pull_request) {
        setResult({ ok: true, message: "Pull request opened on GitHub", url: r.pull_request.url, number: r.pull_request.number });
        showToast(`PR #${r.pull_request.number} opened on GitHub`, "success", "Pull request opened");
      } else {
        setResult({ ok: false, message: "Review accepted, but the pull request didn't open — check your GitHub connection and permission." });
        showToast("The pull request didn't open — check your GitHub connection.", "warning", "PR not opened");
      }
    } catch (e) {
      handleError(e);
    } finally {
      setBusy(null);
    }
  };
  const reject = async () => {
    if (busy) return;
    setBusy("reject");
    setResult(null);
    try {
      const perFile = transplant.diff.map((f) => ({
        path: f.path,
        kind: rejected.has(f.path) ? ("reject" as const) : ("accept" as const),
        reason: rejected.has(f.path) ? "needs manual review" : null,
      }));
      const r = await api.submitReview(transplant.id, "reject", perFile, "rejected on review");
      setResult({ ok: true, message: `Transplant rejected (${r.status}) — no half-transplant ships.` });
    } catch (e) {
      handleError(e);
    } finally {
      setBusy(null);
    }
  };

  const lines = useMemo(() => transplant.diff.map((f) => f.unified_diff.split("\n")), [transplant]);

  return (
    <div className="flex flex-col gap-5">
      <Alert variant={c.approved ? "success" : "warning"}>
        <AlertTitle>
          {c.approved ? <Check /> : <Warn />}
          {c.verdicts.length > 0
            ? `${c.approved ? "Consensus approved" : "Contested"} · ${c.approvals}/${c.panel_size} judges approve`
            : "Ready to open a PR"}
        </AlertTitle>
        <AlertDescription className="mt-1">
          {c.verdicts.length > 0
            ? "Nothing ships without your review — accept to open a PR, or reject any file to block it."
            : "A version bump to a patched release — review the change and accept to open a PR."}
        </AlertDescription>
      </Alert>

      {c.verdicts.length > 0 && (
        <div>
          <div className="eyebrow mb-2.5">Judge verdicts</div>
          <div className="flex flex-col gap-2">
            {c.verdicts.map((v) => (
              <div key={v.judge_name} className="rounded-md border bg-card p-3">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-[13px] font-medium">{v.judge_name}</span>
                  <Badge variant={v.verdict === "approve" ? "success" : "destructive"}>
                    {v.verdict.toUpperCase()}
                  </Badge>
                </div>
                <p className="mt-1.5 text-[12.5px] leading-relaxed text-muted-foreground">{v.rationale}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      <div>
        <div className="eyebrow mb-2.5">Per-file diff</div>
        <div className="flex flex-col gap-3">
          {transplant.diff.map((f, i) => (
            <div key={f.path} className="overflow-hidden rounded-md border">
              <div className="flex items-center justify-between gap-2 border-b bg-muted/50 px-3 py-2">
                <span className="truncate font-mono text-[12.5px] font-medium">{f.path}</span>
                <div className="flex shrink-0 items-center gap-3 text-[12px] text-muted-foreground">
                  <label className="flex cursor-pointer items-center gap-1.5">
                    <input
                      type="radio" name={`rw${i}`} defaultChecked
                      onChange={() => toggle(f.path, false)}
                      style={{ accentColor: "hsl(var(--primary))" }}
                    />
                    accept
                  </label>
                  <label className="flex cursor-pointer items-center gap-1.5">
                    <input
                      type="radio" name={`rw${i}`}
                      onChange={() => toggle(f.path, true)}
                      style={{ accentColor: "hsl(var(--destructive))" }}
                    />
                    reject
                  </label>
                </div>
              </div>
              <pre className="overflow-x-auto bg-card p-3 font-mono text-[11.5px] leading-relaxed">
                {lines[i].map((l, j) => (
                  <span key={j} className={lineClass(l)}>
                    {l}
                    {"\n"}
                  </span>
                ))}
              </pre>
            </div>
          ))}
        </div>
      </div>

      <div className="border-t pt-4">
        <div className="flex flex-wrap items-center gap-2.5">
          <Button disabled={anyReject || busy !== null} onClick={accept}>
            {busy === "accept" ? (
              <>
                <Spinner /> Opening pull request…
              </>
            ) : anyReject ? (
              "Some files rejected — PR blocked"
            ) : (
              "Accept all → open PR"
            )}
          </Button>
          <Button variant="outline" disabled={busy !== null} onClick={reject}>
            {busy === "reject" ? (
              <>
                <Spinner /> Rejecting…
              </>
            ) : (
              "Reject transplant"
            )}
          </Button>
        </div>
        {busy === "accept" && (
          <p className="mt-2.5 text-[12px] text-muted-foreground">
            Creating the branch, committing the files, and opening the PR on GitHub — this can take a few seconds.
          </p>
        )}
        {result &&
          (result.ok && result.url ? (
            <Alert variant="success" className="mt-3">
              <AlertTitle>
                <Check /> {result.message}
              </AlertTitle>
              <AlertDescription className="mt-1">
                <a
                  href={result.url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 font-medium text-success underline underline-offset-2"
                >
                  View pull request #{result.number} <Arrow className="h-3.5 w-3.5" />
                </a>
              </AlertDescription>
            </Alert>
          ) : (
            <Alert variant={result.ok ? "success" : "warning"} className="mt-3">
              <AlertTitle>
                {result.ok ? <Check /> : <Warn />} {result.ok ? "Done" : "Heads up"}
              </AlertTitle>
              <AlertDescription className="mt-1">{result.message}</AlertDescription>
            </Alert>
          ))}
      </div>
    </div>
  );
}
