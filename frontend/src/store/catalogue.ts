import { create } from "zustand";
import { api } from "../api/client";
import type { Competition, MatchCard } from "../api/types";

/** The match list and competitions, fetched once and shared by the home page and search. */
interface Catalogue {
  matches: MatchCard[];
  competitions: Competition[];
  byId: Map<string, MatchCard>;
  status: "idle" | "loading" | "ready" | "error";
  load: (force?: boolean) => Promise<void>;
}

export const useCatalogue = create<Catalogue>((set, get) => ({
  matches: [],
  competitions: [],
  byId: new Map(),
  status: "idle",
  async load(force = false) {
    const { status } = get();
    if (!force && (status === "loading" || status === "ready")) return;
    set({ status: "loading" });
    try {
      const [competitions, matches] = await Promise.all([api.competitions(), api.matches()]);
      set({ competitions, matches, byId: new Map(matches.map((m) => [m.match_id, m])), status: "ready" });
    } catch {
      set({ status: "error" });
    }
  },
}));
