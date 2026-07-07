import { useEffect, useRef, useState } from "react";
import type { PipelineEvent } from "./types";

export interface PipelineView { events: PipelineEvent[]; terminalStage: string | null; }

export function usePipelineStream(incidentId: string | null): PipelineView {
  const [events, setEvents] = useState<PipelineEvent[]>([]);
  const [terminalStage, setTerminalStage] = useState<string | null>(null);
  const seen = useRef<Set<number>>(new Set());

  useEffect(() => {
    if (!incidentId) return;
    seen.current = new Set();
    setEvents([]);
    setTerminalStage(null);
    const source = new EventSource(`/incidents/${incidentId}/stream`);
    source.onmessage = (message) => {
      const event = JSON.parse(message.data) as PipelineEvent;
      if (seen.current.has(event.seq)) return;
      seen.current.add(event.seq);
      setEvents((prev) => [...prev, event]);
      if (event.terminal) {
        setTerminalStage(event.stage);
        source.close();
      }
    };
    source.onerror = () => source.close();
    return () => source.close();
  }, [incidentId]);

  return { events, terminalStage };
}
