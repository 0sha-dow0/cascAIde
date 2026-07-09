import type { ReactNode, SVGProps } from "react";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { ThemeToggle } from "@/components/theme-toggle";
import { Arrow, Bolt, Branch, Check } from "@/components/icons";
import { cn } from "@/lib/utils";

/* Token colors as CSS-var strings, for SVG fills/strokes. */
const C = {
  rose: "hsl(var(--destructive))",
  teal: "hsl(var(--primary))",
  emerald: "hsl(var(--success))",
  amber: "hsl(var(--warning))",
  border: "hsl(var(--border))",
  muted: "hsl(var(--muted-foreground))",
  card: "hsl(var(--card))",
  fg: "hsl(var(--foreground))",
};

/* ---- extra inline icons (match icons.tsx stroke style) ---- */
type P = SVGProps<SVGSVGElement>;
const Ico = ({ children, ...p }: P) => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" {...p}>{children}</svg>
);
const Radius = (p: P) => <Ico {...p}><circle cx="12" cy="12" r="3" /><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1" /></Ico>;
const Gavel = (p: P) => <Ico {...p}><path d="m14 13-7.5 7.5a2.1 2.1 0 0 1-3-3L11 10M14 13l3-3M11 10l3-3M8.5 6.5l6 6M16 3l5 5M18.5 5.5 15 9M4 21h9" /></Ico>;
const Brain = (p: P) => <Ico {...p}><path d="M12 5a3 3 0 0 0-6 .5A2.5 2.5 0 0 0 4 8a2.5 2.5 0 0 0 .5 4.5A2.5 2.5 0 0 0 7 17a3 3 0 0 0 5 1M12 5a3 3 0 0 1 6 .5A2.5 2.5 0 0 1 20 8a2.5 2.5 0 0 1-.5 4.5A2.5 2.5 0 0 1 17 17a3 3 0 0 1-5 1M12 5v14" /></Ico>;
const Shield = (p: P) => <Ico {...p}><path d="M12 3 5 6v5c0 4.4 3 7.8 7 9 4-1.2 7-4.6 7-9V6l-7-3Z" /><path d="m9.5 12 1.8 1.8 3.4-3.6" /></Ico>;
const PR = (p: P) => <Ico {...p}><circle cx="6" cy="6" r="2.5" /><circle cx="6" cy="18" r="2.5" /><circle cx="18" cy="18" r="2.5" /><path d="M6 8.5v7M18 15.5V13a4 4 0 0 0-4-4h-3.5M12 6.5 10 9l2.5 1.5" /></Ico>;
const Github = (p: P) => <Ico {...p}><path d="M9 19c-4.3 1.4-4.3-2.5-6-3m12 5v-3.5c0-1 .1-1.4-.5-2 2.8-.3 5.5-1.4 5.5-6a4.6 4.6 0 0 0-1.3-3.2 4.2 4.2 0 0 0-.1-3.2s-1.1-.3-3.5 1.3a12 12 0 0 0-6 0C6.7 2.6 5.6 2.9 5.6 2.9a4.2 4.2 0 0 0-.1 3.2A4.6 4.6 0 0 0 4 9.3c0 4.6 2.7 5.7 5.5 6-.6.6-.6 1.2-.5 2V21" /></Ico>;

/* ============================ page ============================ */
export function Landing({ onLaunch }: { onLaunch: () => void }) {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <Nav onLaunch={onLaunch} />
      <Hero onLaunch={onLaunch} />
      <TrustStrip />
      <Features />
      <Pipeline />
      <Showcase onLaunch={onLaunch} />
      <CtaBand onLaunch={onLaunch} />
      <Footer />
    </div>
  );
}

function Nav({ onLaunch }: { onLaunch: () => void }) {
  return (
    <header className="fixed inset-x-0 top-0 z-50 border-b border-border/70 bg-background/80 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-5">
        <a href="#top" className="flex items-center gap-2.5">
          <span className="grad-brand flex h-7 w-7 items-center justify-center rounded-[8px] text-[15px] font-bold text-white shadow-sm">⟩</span>
          <span className="grad-text font-display text-[16px] font-bold tracking-tight">cascAIde</span>
        </a>
        <nav className="hidden items-center gap-7 text-[13px] text-muted-foreground md:flex">
          <a href="#features" className="transition-colors hover:text-foreground">Features</a>
          <a href="#pipeline" className="transition-colors hover:text-foreground">How it works</a>
          <a href="#showcase" className="transition-colors hover:text-foreground">In action</a>
        </nav>
        <div className="flex items-center gap-1.5">
          <ThemeToggle />
          <Button size="sm" onClick={onLaunch}>Launch app <Arrow /></Button>
        </div>
      </div>
    </header>
  );
}

function Hero({ onLaunch }: { onLaunch: () => void }) {
  return (
    <section id="top" className="relative overflow-hidden pt-14">
      <div className="grid-fade pointer-events-none absolute inset-0" />
      <div className="relative mx-auto grid max-w-6xl items-center gap-10 px-5 pb-16 pt-16 lg:grid-cols-[1.05fr_1fr] lg:pb-24 lg:pt-24">
        <div>
          <span className="grad-ring inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[11.5px] font-medium text-muted-foreground">
            <span className="h-1.5 w-1.5 rounded-full bg-primary la-blink" />
            Autonomous dependency security
          </span>
          <h1 className="mt-5 font-display text-[40px] font-bold leading-[1.05] tracking-tight sm:text-[54px]">
            Autonomous surgery for your{" "}
            <span className="la-sheen">vulnerable dependencies</span>.
          </h1>
          <p className="mt-5 max-w-xl text-[15px] leading-relaxed text-muted-foreground">
            cascAIde scans a repo, maps a CVE&apos;s real blast radius in Neo4j, rewrites the vulnerable
            package <code className="rounded bg-muted px-1 py-0.5 font-mono text-[13px] text-foreground">axios&nbsp;→&nbsp;fetch</code>{" "}
            across every call site, proves behavior with a 4-judge consensus, and opens the PR —
            grounded in Cognee code memory.
          </p>
          <div className="mt-7 flex flex-wrap items-center gap-3">
            <Button size="lg" onClick={onLaunch}>Launch cascAIde <Arrow /></Button>
            <a href="#pipeline" className={cn(buttonVariants({ variant: "outline", size: "lg" }))}>
              See how it works
            </a>
          </div>
          <div className="mt-6 flex flex-wrap items-center gap-x-5 gap-y-2 text-[12px] text-muted-foreground">
            <span className="inline-flex items-center gap-1.5"><Check className="text-success" /> Real GHSA advisories</span>
            <span className="inline-flex items-center gap-1.5"><Check className="text-success" /> Live Neo4j graph</span>
            <span className="inline-flex items-center gap-1.5"><Check className="text-success" /> No mocks in production</span>
          </div>
        </div>
        <HeroGraphic />
      </div>
    </section>
  );
}

/* Signature: files -> vulnerable axios (rose blast radius) -> transplant -> fetch (teal). */
function HeroGraphic() {
  const files: [number, number, number, string][] = [
    [80, 74, 108, "server.js"],
    [64, 172, 122, "products.js"],
    [84, 270, 114, "inventory.js"],
  ];
  const AX = { cx: 250, cy: 172, w: 84 };
  const FE = { cx: 392, cy: 172, w: 74 };
  return (
    <div className="la-float relative mx-auto w-full max-w-[480px]">
      <div className="grad-ring rounded-2xl bg-card/60 p-3 shadow-xl backdrop-blur-sm">
        <svg viewBox="0 0 460 344" className="w-full" role="img" aria-label="Dependency blast radius transplanted from axios to fetch">
          {/* edges: files -> axios (rose, flowing) */}
          {files.map(([cx, cy, w], i) => (
            <line key={i} x1={cx + w / 2} y1={cy} x2={AX.cx - AX.w / 2} y2={AX.cy}
              className="la-flow" style={{ stroke: C.rose, strokeWidth: 1.6, opacity: 0.85 }} />
          ))}
          {/* edge: axios -> fetch (teal transplant) */}
          <line x1={AX.cx + AX.w / 2} y1={AX.cy} x2={FE.cx - FE.w / 2} y2={FE.cy}
            className="la-flow" style={{ stroke: C.teal, strokeWidth: 2 }} />
          {/* file nodes */}
          {files.map(([cx, cy, w], i) => (
            <g key={i}>
              <rect x={cx - w / 2} y={cy - 14} width={w} height={28} rx={8} style={{ fill: C.card, stroke: C.border }} />
              <text x={cx} y={cy + 4} textAnchor="middle" style={{ fill: C.muted, font: "600 11px var(--font-mono)" }}>{["server.js", "products.js", "inventory.js"][i]}</text>
            </g>
          ))}
          {/* halo + axios (vulnerable) */}
          <circle cx={AX.cx} cy={AX.cy} r={24} className="la-halo" style={{ fill: "none", stroke: C.rose, strokeWidth: 2 }} />
          <rect x={AX.cx - AX.w / 2} y={AX.cy - 18} width={AX.w} height={36} rx={18}
            style={{ fill: "hsl(var(--destructive) / 0.14)", stroke: C.rose, strokeWidth: 1.5 }} />
          <text x={AX.cx} y={AX.cy + 4} textAnchor="middle" style={{ fill: C.rose, font: "700 12.5px var(--font-mono)" }}>⚠ axios</text>
          {/* fetch (cured) */}
          <rect x={FE.cx - FE.w / 2} y={FE.cy - 18} width={FE.w} height={36} rx={18}
            style={{ fill: "hsl(var(--primary) / 0.14)", stroke: C.teal, strokeWidth: 1.5 }} />
          <text x={FE.cx} y={FE.cy + 4} textAnchor="middle" style={{ fill: C.teal, font: "700 12.5px var(--font-mono)" }}>fetch</text>
          {/* transplant label */}
          <text x={321} y={158} textAnchor="middle" style={{ fill: C.muted, font: "600 10px var(--font-mono)" }}>transplant</text>
          {/* blast-radius chip */}
          <g transform="translate(150, 300)">
            <rect x={-6} y={-13} width={172} height={24} rx={12} style={{ fill: "hsl(var(--destructive) / 0.08)", stroke: "hsl(var(--destructive) / 0.35)" }} />
            <circle cx={8} cy={-1} r={3} style={{ fill: C.rose }} />
            <text x={20} y={3} style={{ fill: C.rose, font: "600 11px var(--font-mono)" }}>blast radius · 3 files</text>
          </g>
        </svg>
      </div>
    </div>
  );
}

function TrustStrip() {
  const items = ["Neo4j Aura", "GitHub Advisory DB", "Groq", "Cognee", "Daytona"];
  return (
    <section className="border-y border-border/70 bg-muted/30">
      <div className="mx-auto flex max-w-6xl flex-col items-center gap-3 px-5 py-6 sm:flex-row sm:justify-between">
        <span className="eyebrow">Real data · live integrations</span>
        <div className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2">
          {items.map((i) => (
            <span key={i} className="font-mono text-[12.5px] font-medium text-muted-foreground">{i}</span>
          ))}
        </div>
      </div>
    </section>
  );
}

function Features() {
  const items: { icon: ReactNode; title: string; body: string; span?: boolean; visual?: ReactNode }[] = [
    { icon: <Radius />, title: "Blast-radius graph", body: "Every file that transitively imports the CVE — mapped in Neo4j, rendered as a live, click-to-explode graph.", span: true, visual: <MiniGraph /> },
    { icon: <Bolt />, title: "Autonomous transplant", body: "Rewrites axios → fetch across every call site, including the aliased ones a grep misses." },
    { icon: <Gavel />, title: "4-judge consensus", body: "Correctness, security, minimality and recipe-fidelity judges gate every change before you see it." },
    { icon: <Brain />, title: "Explore, grounded", body: "One click turns the repo into Cognee code memory and returns a step-by-step implementation plan." },
    { icon: <Shield />, title: "Real GHSA scoring", body: "CVSS severity + graph centrality priority, straight from the live GitHub Advisory Database." },
    { icon: <PR />, title: "Ships the PR", body: "Accept the diff and cascAIde opens the pull request — the fix lands where it belongs." },
  ];
  return (
    <section id="features" className="mx-auto max-w-6xl px-5 py-20 lg:py-28">
      <SectionHead eyebrow="Capabilities" title="From vulnerable to verified — end to end." sub="Not a linter. cascAIde performs the whole operation: diagnosis, surgery, proof, and delivery." />
      <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((it) => (
          <div key={it.title} className={`group rounded-xl border bg-card p-5 transition-colors hover:border-primary/40 ${it.span ? "sm:col-span-2 lg:row-span-2" : ""}`}>
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary">{it.icon}</div>
            <h3 className="mt-4 font-display text-[16px] font-semibold">{it.title}</h3>
            <p className="mt-1.5 text-[13.5px] leading-relaxed text-muted-foreground">{it.body}</p>
            {it.visual}
          </div>
        ))}
      </div>
    </section>
  );
}

/* Small stylized graph used inside the wide feature card. */
function MiniGraph() {
  return (
    <svg viewBox="0 0 300 150" className="mt-5 w-full">
      {[[40, 40], [40, 110]].map(([x, y], i) => (
        <line key={i} x1={x + 34} y1={y} x2={146} y2={75} className="la-flow" style={{ stroke: C.rose, strokeWidth: 1.4, opacity: 0.8 }} />
      ))}
      <line x1={182} y1={75} x2={244} y2={75} className="la-flow" style={{ stroke: C.teal, strokeWidth: 1.8 }} />
      {[[40, 40, "api.js"], [40, 110, "db.js"]].map(([x, y, l], i) => (
        <g key={i}>
          <rect x={(x as number) - 34} y={(y as number) - 12} width={68} height={24} rx={7} style={{ fill: C.card, stroke: C.border }} />
          <text x={x as number} y={(y as number) + 4} textAnchor="middle" style={{ fill: C.muted, font: "600 10px var(--font-mono)" }}>{l}</text>
        </g>
      ))}
      <circle cx={164} cy={75} r={17} className="la-halo" style={{ fill: "none", stroke: C.rose, strokeWidth: 1.6 }} />
      <rect x={140} y={62} width={48} height={26} rx={13} style={{ fill: "hsl(var(--destructive) / 0.14)", stroke: C.rose }} />
      <text x={164} y={79} textAnchor="middle" style={{ fill: C.rose, font: "700 10.5px var(--font-mono)" }}>axios</text>
      <rect x={244} y={62} width={48} height={26} rx={13} style={{ fill: "hsl(var(--primary) / 0.14)", stroke: C.teal }} />
      <text x={268} y={79} textAnchor="middle" style={{ fill: C.teal, font: "700 10.5px var(--font-mono)" }}>fetch</text>
    </svg>
  );
}

function Pipeline() {
  const steps = [
    { n: "Scan", d: "Clone + parse imports" },
    { n: "Graph", d: "Neo4j blast radius" },
    { n: "CVE", d: "GHSA advisory + score" },
    { n: "Strategy", d: "Ranked mitigations" },
    { n: "Transplant", d: "axios → fetch" },
    { n: "Judge", d: "4-judge consensus" },
    { n: "PR", d: "You accept · it ships" },
  ];
  return (
    <section id="pipeline" className="border-y border-border/70 bg-muted/30">
      <div className="mx-auto max-w-6xl px-5 py-20 lg:py-28">
        <SectionHead eyebrow="The pipeline" title="Seven steps from scan to shipped fix." sub="Every stage streams live — and a human gates the diff before anything opens a PR." />
        <div className="relative mt-12">
          <div className="pointer-events-none absolute left-0 right-0 top-5 hidden h-px bg-gradient-to-r from-transparent via-primary/40 to-transparent lg:block" />
          <ol className="grid gap-4 sm:grid-cols-2 lg:grid-cols-7">
            {steps.map((s, i) => (
              <li key={s.n} className="relative flex flex-col items-center text-center">
                <span className="grad-brand relative z-10 flex h-10 w-10 items-center justify-center rounded-full text-[13px] font-bold text-white shadow-sm">{i + 1}</span>
                <h4 className="mt-3 font-display text-[14px] font-semibold">{s.n}</h4>
                <p className="mt-0.5 text-[11.5px] leading-snug text-muted-foreground">{s.d}</p>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}

function Showcase({ onLaunch }: { onLaunch: () => void }) {
  return (
    <section id="showcase" className="relative overflow-hidden py-20 lg:py-28">
      <div className="grid-fade pointer-events-none absolute inset-0" />
      <div className="relative mx-auto max-w-6xl px-5">
      <SectionHead eyebrow="In action" title="See the operation, not a marketing render." sub="This is the actual product surface — a real graph and a real Cognee-grounded plan." />
      <div className="mt-12 grid gap-6 lg:grid-cols-2">
        <Window title="cascAIde · dependency graph">
          <div className="p-4">
            <div className="mb-3 inline-flex items-center gap-1.5 rounded-full border border-destructive/30 bg-destructive/[0.06] px-2.5 py-1 text-[11px] font-medium text-destructive">
              <span className="h-1.5 w-1.5 rounded-full bg-destructive" /> blast radius · 3 files · 1 test breaks
            </div>
            <MiniGraph />
          </div>
        </Window>
        <Window title="cascAIde · implementation plan">
          <div className="space-y-2.5 p-4">
            <div className="flex items-center gap-2">
              <Badge variant="primary" className="font-mono">Transplant → fetch</Badge>
              <span className="text-[11px] text-muted-foreground">grounded in Cognee code memory</span>
            </div>
            {[
              ["Add a fetch helper", ["src/httpClient.js"]],
              ["Repoint getJson / postJson", ["src/clients/upstream.js"]],
              ["Update checkStock", ["src/services/inventory.js"]],
            ].map(([t, files], i) => (
              <div key={i} className="rounded-lg border bg-background/60 p-2.5">
                <div className="flex items-start gap-2.5">
                  <span className="grad-brand mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-bold text-white">{i + 1}</span>
                  <div>
                    <div className="text-[12.5px] font-semibold">{t as string}</div>
                    <div className="mt-1.5 flex flex-wrap gap-1.5">
                      {(files as string[]).map((f) => (
                        <code key={f} className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10.5px] text-foreground">{f}</code>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Window>
      </div>
      <div className="mt-8 flex justify-center">
        <Button size="lg" onClick={onLaunch}>Try it on a real repo <Arrow /></Button>
      </div>
      </div>
    </section>
  );
}

function Window({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="grad-ring overflow-hidden rounded-xl bg-card shadow-lg">
      <div className="flex items-center gap-2 border-b bg-muted/40 px-3 py-2">
        <span className="h-2.5 w-2.5 rounded-full bg-destructive/60" />
        <span className="h-2.5 w-2.5 rounded-full bg-warning/70" />
        <span className="h-2.5 w-2.5 rounded-full bg-success/70" />
        <span className="ml-2 font-mono text-[11px] text-muted-foreground">{title}</span>
      </div>
      {children}
    </div>
  );
}

function CtaBand({ onLaunch }: { onLaunch: () => void }) {
  return (
    <section className="mx-auto max-w-6xl px-5 pb-24">
      <div className="grad-brand relative overflow-hidden rounded-3xl px-8 py-14 text-center shadow-xl">
        <div className="grid-fade pointer-events-none absolute inset-0 opacity-20" />
        <h2 className="relative font-display text-[30px] font-bold tracking-tight text-white sm:text-[38px]">Ready to operate?</h2>
        <p className="relative mx-auto mt-3 max-w-lg text-[15px] leading-relaxed text-white/85">
          Point cascAIde at any public repo. Watch it find the blast radius, transplant the fix, and hand you a PR.
        </p>
        <div className="relative mt-7 flex justify-center">
          <Button size="lg" variant="secondary" onClick={onLaunch} className="bg-white text-[hsl(var(--grad-to))] hover:bg-white/90">
            Launch cascAIde <Arrow />
          </Button>
        </div>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="border-t border-border/70">
      <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 px-5 py-8 text-[12.5px] text-muted-foreground sm:flex-row">
        <div className="flex items-center gap-2.5">
          <span className="grad-brand flex h-6 w-6 items-center justify-center rounded-[7px] text-[13px] font-bold text-white">⟩</span>
          <span className="font-mono">cascAIde — built for HackwithBay 3.0</span>
        </div>
        <div className="flex items-center gap-5">
          <span className="inline-flex items-center gap-1.5"><Branch className="h-3.5 w-3.5" /> autonomous transplants</span>
          <a href="https://github.com" className="inline-flex items-center gap-1.5 transition-colors hover:text-foreground"><Github className="h-4 w-4" /> GitHub</a>
        </div>
      </div>
    </footer>
  );
}

function SectionHead({ eyebrow, title, sub }: { eyebrow: string; title: string; sub: string }) {
  return (
    <div className="max-w-2xl">
      <span className="eyebrow">{eyebrow}</span>
      <h2 className="mt-2 font-display text-[28px] font-bold leading-tight tracking-tight sm:text-[34px]">{title}</h2>
      <p className="mt-3 text-[15px] leading-relaxed text-muted-foreground">{sub}</p>
    </div>
  );
}
