// Butterbase session + app-config helpers. When auth is not required (fakes /
// pre-cutover), the app falls back to the demo token and no sign-in is shown.

export interface AppConfig {
  auth_required: boolean;
  butterbase_host: string | null;
  app_id: string | null;
}

export interface Session {
  access_token: string;
  refresh_token: string;
}

const SESSION_KEY = "cascaide.session";
const DEMO_TOKEN = "demo-token";

let _configPromise: Promise<AppConfig> | null = null;

export function loadConfig(): Promise<AppConfig> {
  if (!_configPromise) {
    _configPromise = fetch("/config")
      .then((r) => r.json() as Promise<AppConfig>)
      .catch(() => ({ auth_required: false, butterbase_host: null, app_id: null }));
  }
  return _configPromise;
}

export function getSession(): Session | null {
  const raw = localStorage.getItem(SESSION_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as Session;
  } catch {
    return null;
  }
}

export function setSession(s: Session): void {
  localStorage.setItem(SESSION_KEY, JSON.stringify(s));
}

export function clearSession(): void {
  localStorage.removeItem(SESSION_KEY);
}

/** The bearer token every API request sends: the real JWT if signed in, else the demo token. */
export function bearerToken(): string {
  return getSession()?.access_token ?? DEMO_TOKEN;
}

/** Exchange the refresh token for a fresh access token (Butterbase rotates both). Returns success. */
export async function refreshSession(): Promise<boolean> {
  const config = await loadConfig();
  const s = getSession();
  if (!config.butterbase_host || !config.app_id || !s?.refresh_token) return false;
  try {
    const res = await fetch(`${config.butterbase_host}/auth/${config.app_id}/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: s.refresh_token }),
    });
    if (!res.ok) return false;
    const data = (await res.json()) as { access_token?: string; refresh_token?: string };
    if (!data.access_token) return false;
    setSession({ access_token: data.access_token, refresh_token: data.refresh_token ?? s.refresh_token });
    return true;
  } catch {
    return false;
  }
}

/** Redirect the browser into Butterbase's GitHub OAuth flow; it returns to the app root with tokens. */
export function signInWithGitHub(config: AppConfig): void {
  if (!config.butterbase_host || !config.app_id) return;
  const redirectTo = `${window.location.origin}/`;
  const url =
    `${config.butterbase_host}/auth/${config.app_id}/oauth/github` +
    `?redirect_to=${encodeURIComponent(redirectTo)}`;
  window.location.href = url;
}

/**
 * On load, Butterbase's OAuth callback lands us at the app root with
 * ?access_token=...&refresh_token=... — capture, persist, and clean the URL.
 * Returns true if a session was just captured.
 */
export function captureOAuthCallback(): boolean {
  const params = new URLSearchParams(window.location.search);
  const accessToken = params.get("access_token");
  if (!accessToken) return false;
  setSession({ access_token: accessToken, refresh_token: params.get("refresh_token") ?? "" });
  window.history.replaceState({}, "", `${window.location.origin}/#console`);
  return true;
}
