import { useEffect, useState } from "react";
import App from "./App";
import { Landing } from "./Landing";
import { SignIn } from "./SignIn";
import { Toaster } from "./toast";
import {
  captureOAuthCallback,
  clearSession,
  getSession,
  loadConfig,
  type AppConfig,
  type Session,
} from "./session";

function currentView(): "console" | "home" {
  const hash = window.location.hash.replace("#", "");
  return hash === "console" || hash === "app" ? "console" : "home";
}

export default function Root() {
  const [view, setView] = useState<"console" | "home">(currentView);
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [session, setSession] = useState<Session | null>(getSession());

  useEffect(() => {
    if (captureOAuthCallback()) {
      setSession(getSession());
      setView("console");
    }
    void loadConfig().then(setConfig);
    const onHashChange = () => setView(currentView());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  useEffect(() => {
    if (view === "console") window.scrollTo(0, 0);
  }, [view]);

  const signOut = () => {
    clearSession();
    setSession(null);
    window.location.hash = "";
  };

  const content =
    view === "console"
      ? config === null
        ? null // brief blank while /config resolves
        : config.auth_required && session === null
          ? <SignIn config={config} />
          : <App config={config} session={session} onSignOut={signOut} />
      : <Landing onLaunch={() => (window.location.hash = "console")} />;

  return (
    <>
      {content}
      <Toaster />
    </>
  );
}
