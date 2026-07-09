import type { SVGProps } from "react";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/theme-toggle";
import type { AppConfig } from "./session";
import { signInWithGitHub } from "./session";

function GithubIcon(p: SVGProps<SVGSVGElement>) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" {...p}>
      <path d="M9 19c-4.3 1.4-4.3-2.5-6-3m12 5v-3.5c0-1 .1-1.4-.5-2 2.8-.3 5.5-1.4 5.5-6a4.6 4.6 0 0 0-1.3-3.2 4.2 4.2 0 0 0-.1-3.2s-1.1-.3-3.5 1.3a12 12 0 0 0-6 0C6.7 2.6 5.6 2.9 5.6 2.9a4.2 4.2 0 0 0-.1 3.2A4.6 4.6 0 0 0 4 9.3c0 4.6 2.7 5.7 5.5 6-.6.6-.6 1.2-.5 2V21" />
    </svg>
  );
}

export function SignIn({ config }: { config: AppConfig }) {
  return (
    <div className="relative flex min-h-screen items-center justify-center bg-background px-5">
      <div className="grid-fade pointer-events-none absolute inset-0" />
      <div className="absolute right-4 top-4">
        <ThemeToggle />
      </div>
      <div className="grad-ring relative w-full max-w-md rounded-2xl bg-card/70 p-8 shadow-xl backdrop-blur-sm">
        <div className="flex items-center gap-2.5">
          <span className="grad-brand flex h-8 w-8 items-center justify-center rounded-[9px] text-[16px] font-bold text-white shadow-sm">⟩</span>
          <span className="grad-text font-display text-[18px] font-bold tracking-tight">cascAIde</span>
        </div>
        <h1 className="mt-6 font-display text-[24px] font-bold tracking-tight">Sign in to operate</h1>
        <p className="mt-2 text-[13.5px] leading-relaxed text-muted-foreground">
          cascAIde acts on GitHub <span className="font-medium text-foreground">as you</span> — so it can check
          your permission on a repo before firing a CVE, and open the pull request on your behalf.
        </p>
        <Button className="mt-6 w-full" size="lg" onClick={() => signInWithGitHub(config)}>
          <GithubIcon /> Sign in with GitHub
        </Button>
        <a
          href="#"
          className="mt-4 block text-center text-[12.5px] text-muted-foreground transition-colors hover:text-foreground"
        >
          ← Back to home
        </a>
      </div>
    </div>
  );
}
