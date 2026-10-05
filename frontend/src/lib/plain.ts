import type { Backtest } from "../api/types";

/** The backtest's short answer in one plain sentence. Shared with the backtest page. */
export function bookiesAnswer(bt: Backtest): string {
  const sig = bt.strategies.filter((s) => s.roi_ci95[0] > 0);
  const neg = bt.strategies.filter((s) => s.roi_ci95[1] < 0);
  if (sig.length) return "Short answer: yes, and by more than luck would explain.";
  if (neg.length === bt.strategies.length) return "Short answer: no. The bookies were sharper.";
  return "Short answer: not clearly. Some strategies made money, but not by more than luck could explain.";
}

