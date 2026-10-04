import { create } from "zustand";

interface UiState {
  searchOpen: boolean;
  /** Query the palette starts with when opened from an example. */
  searchSeed: string;
  setSearchOpen: (open: boolean, seed?: string) => void;
}

export const useUi = create<UiState>((set) => ({
  searchOpen: false,
  searchSeed: "",
  setSearchOpen: (open, seed = "") => set({ searchOpen: open, searchSeed: seed }),
}));

interface PlayerUi {
  playerId: number | null;
  openPlayer: (id: number | null) => void;
}

export const usePlayerUi = create<PlayerUi>((set) => ({
  playerId: null,
  openPlayer: (id) => set({ playerId: id }),
}));
