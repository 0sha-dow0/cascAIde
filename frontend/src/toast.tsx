import { useEffect, useState, type ReactNode } from "react";
import { Check, Cross, Spinner, Warn } from "@/components/icons";

export type ToastVariant = "denied" | "warning" | "success" | "info";
interface ToastMsg {
  id: number;
  title: string;
  message: string;
  variant: ToastVariant;
}

type Listener = (t: ToastMsg) => void;
const listeners = new Set<Listener>();
let counter = 0;

const _TITLES: Record<ToastVariant, string> = {
  denied: "Access denied",
  warning: "Action needed",
  success: "Done",
  info: "Working…",
};

/** Pop a snackbar from anywhere (no prop drilling). Auto-dismisses after a few seconds. */
export function showToast(message: string, variant: ToastVariant = "denied", title?: string): void {
  counter += 1;
  const toast: ToastMsg = { id: counter, message, variant, title: title ?? _TITLES[variant] };
  listeners.forEach((l) => l(toast));
}

const _DURATION_MS = 5000;

const _STYLES: Record<ToastVariant, { ring: string; icon: string; node: ReactNode }> = {
  denied: { ring: "border-l-destructive", icon: "text-destructive", node: <Warn /> },
  warning: { ring: "border-l-warning", icon: "text-warning", node: <Warn /> },
  success: { ring: "border-l-success", icon: "text-success", node: <Check /> },
  info: { ring: "border-l-primary", icon: "text-primary", node: <Spinner /> },
};

export function Toaster() {
  const [toasts, setToasts] = useState<ToastMsg[]>([]);

  useEffect(() => {
    const listener: Listener = (t) => {
      setToasts((prev) => [...prev, t]);
      window.setTimeout(
        () => setToasts((prev) => prev.filter((x) => x.id !== t.id)),
        _DURATION_MS,
      );
    };
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  }, []);

  const dismiss = (id: number) => setToasts((prev) => prev.filter((x) => x.id !== id));

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-5 z-[60] flex flex-col items-center gap-2 px-4">
      {toasts.map((t) => {
        const s = _STYLES[t.variant];
        return (
          <div
            key={t.id}
            role="status"
            className={`toast-in pointer-events-auto flex w-full max-w-md items-start gap-3 rounded-xl border border-l-[3px] bg-card px-4 py-3 shadow-xl ${s.ring}`}
          >
            <span className={`mt-0.5 shrink-0 ${s.icon}`}>{s.node}</span>
            <div className="min-w-0 flex-1">
              <div className="text-[13px] font-semibold">{t.title}</div>
              <p className="mt-0.5 text-[12.5px] leading-snug text-muted-foreground">{t.message}</p>
            </div>
            <button
              aria-label="Dismiss"
              onClick={() => dismiss(t.id)}
              className="-mr-1 -mt-0.5 rounded p-1 text-muted-foreground transition-colors hover:text-foreground"
            >
              <Cross className="h-3.5 w-3.5" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
