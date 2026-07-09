import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Check } from "@/components/icons";
import type { AppConfig, Session } from "../session";

interface Profile {
  display_name?: string;
  email?: string;
  avatar_url?: string;
}

export function AccountMenu({
  config,
  session,
  onSignOut,
}: {
  config: AppConfig;
  session: Session;
  onSignOut: () => void;
}) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [connected, setConnected] = useState<boolean | null>(null);
  const host = config.butterbase_host;
  const appId = config.app_id;
  const auth = { Authorization: `Bearer ${session.access_token}` };

  useEffect(() => {
    if (!host || !appId) return;
    void fetch(`${host}/auth/${appId}/me`, { headers: auth })
      .then((r) => (r.ok ? (r.json() as Promise<Profile>) : null))
      .then(setProfile)
      .catch(() => setProfile(null));
    void fetch(`${host}/v1/${appId}/integrations/connections`, { headers: auth })
      .then((r) => (r.ok ? r.json() : { connections: [] }))
      .then((d: { connections?: { toolkit_slug: string; status?: string }[] }) =>
        setConnected((d.connections ?? []).some((c) => c.toolkit_slug === "github")),
      )
      .catch(() => setConnected(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [host, appId]);

  const connectGitHub = async () => {
    if (!host || !appId) return;
    const res = await fetch(`${host}/v1/${appId}/integrations/connect`, {
      method: "POST",
      headers: { ...auth, "Content-Type": "application/json" },
      body: JSON.stringify({ toolkit: "github", redirectUrl: `${window.location.origin}/#console` }),
    });
    const data = (await res.json()) as { authUrl?: string };
    if (data.authUrl) window.location.href = data.authUrl;
  };

  const name = profile?.display_name || profile?.email || "signed in";

  return (
    <div className="flex items-center gap-2">
      {connected === false && (
        <Button size="sm" variant="outline" onClick={connectGitHub}>
          <span className="hidden sm:inline">Connect GitHub</span>
          <span className="sm:hidden">Connect</span>
        </Button>
      )}
      {connected === true && (
        <Badge variant="success" className="gap-1">
          <Check className="h-3 w-3" />
          <span className="hidden sm:inline">GitHub connected</span>
          <span className="sm:hidden">GitHub</span>
        </Badge>
      )}
      <div className="flex items-center gap-1.5">
        {profile?.avatar_url ? (
          <img src={profile.avatar_url} alt="" className="h-6 w-6 rounded-full border" />
        ) : (
          <span className="grad-brand flex h-6 w-6 items-center justify-center rounded-full text-[11px] font-bold text-white">
            {name.slice(0, 1).toUpperCase()}
          </span>
        )}
        <span className="hidden text-[12.5px] text-muted-foreground sm:inline">{name}</span>
      </div>
      <Button size="sm" variant="ghost" onClick={onSignOut}>
        Sign out
      </Button>
    </div>
  );
}
