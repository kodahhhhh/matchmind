/** One plain sentence per stat, for fans who don't speak analytics. Shown in Explain tooltips. */
export const GLOSSARY = {
  possession: "Share of the passes each team made. More of the ball, not necessarily more danger.",
  territory: "How much of the play happened near the opponent's goal (the final third).",
  chances: "Chance quality, also called xG (expected goals). Every shot is worth the chance it goes in, so 1.0 is about one goal's worth of chances.",
  shots: "Every attempt on goal, on or off target.",
  momentum: "Who is on top right now: which team's recent actions are making a goal more likely.",
  impact: "How much a player's actions raised their team's chance of scoring, or lowered the opponent's. Higher is better.",
  danger: "How close the move came to producing a goal, judged by how much each action raised the scoring chance.",
} as const;

export type GlossaryKey = keyof typeof GLOSSARY;
