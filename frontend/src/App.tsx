import { BrowserRouter, Route, Routes, useLocation } from "react-router";
import { AnimatePresence, motion } from "motion/react";
import { MatchBrowser } from "./components/browser/MatchBrowser";
import { MatchView } from "./components/match/MatchView";
import { SearchPalette } from "./components/search/SearchPalette";
import { BacktestPage } from "./components/backtest/BacktestPage";
import { LeaderboardPage } from "./components/players/LeaderboardPage";
import { PlayerDrawer } from "./components/players/PlayerDrawer";

function AnimatedRoutes() {
  const location = useLocation();
  // match → match navigation keeps the shell mounted; page-level changes cross-fade
  const key = location.pathname.split("/")[1] || "home";
  return (
    <AnimatePresence mode="wait">
      <motion.div key={key} className="h-full"
        initial={{ opacity: 0, y: 10, filter: "blur(4px)" }} animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
        exit={{ opacity: 0, y: -6, filter: "blur(4px)" }} transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}>
        <Routes location={location}>
          <Route path="/" element={<MatchBrowser />} />
          <Route path="/match/:id" element={<MatchView />} />
          <Route path="/backtest" element={<BacktestPage />} />
          <Route path="/players" element={<LeaderboardPage />} />
        </Routes>
      </motion.div>
    </AnimatePresence>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AnimatedRoutes />
      <SearchPalette />
      <PlayerDrawer />
    </BrowserRouter>
  );
}
