import type { LeaderboardRow } from "../../api/types";

/** Underrated = genuinely high value added (top 40% of the list) at the lowest market prices. */
export function pickUnderrated(rows: LeaderboardRow[], n = 8): LeaderboardRow[] {
  const cut = Math.max(5, Math.ceil(rows.length * 0.4));
  return rows
    .filter((r) => r.underrated_score != null && r.metric_rank <= cut)
    .sort((a, b) => b.underrated_score! - a.underrated_score!)
    .slice(0, n);
}

/** Tournaments need fewer minutes to qualify than league seasons. */
export const minMinutes = (competition: string) =>
  /Bundesliga|Liga|Premier|Ligue|Serie/.test(competition) ? 900 : 270;
