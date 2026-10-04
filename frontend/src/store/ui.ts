import { create } from "zustand";

interface UiState {
  searchOpen: boolean;
  setSearchOpen: (open: boolean) => void;
}

export const useUi = create<UiState>((set) => ({
  searchOpen: false,
  setSearchOpen: (open) => set({ searchOpen: open }),
}));

interface PlayerUi {
  playerId: number | null;
  openPlayer: (id: number | null) => void;
}

export const usePlayerUi = create<PlayerUi>((set) => ({
  playerId: null,
  openPlayer: (id) => set({ playerId: id }),
}));
