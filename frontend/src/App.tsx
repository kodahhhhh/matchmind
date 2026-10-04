import { BrowserRouter, Route, Routes, useLocation } from "react-router";
import { AnimatePresence, MotionConfig, motion } from "motion/react";
import { MatchBrowser } from "./components/browser/MatchBrowser";
import { MatchView } from "./components/match/MatchView";
import { SearchPalette } from "./components/search/SearchPalette";
import { BacktestPage } from "./components/backtest/BacktestPage";
import { LeaderboardPage } from "./components/players/LeaderboardPage";
import { PlayerDrawer } from "./components/players/PlayerDrawer";
import { NotFound } from "./components/ui/NotFound";

function AnimatedRoutes() {
  const location = useLocation();
  // match → match navigation keeps the shell mounted; page-level changes cross-fade
  const key = location.pathname.split("/")[1] || "home";
  return (
    <AnimatePresence mode="wait">
      <motion.div key={key} className="h-full"
        initial={{ opacity: 0, y: 8, filter: "blur(3px)" }} animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
        exit={{ opacity: 0, filter: "blur(3px)", transition: { duration: 0.15, ease: "easeOut" } }}
        transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}>
        <Routes location={location}>
          <Route path="/" element={<MatchBrowser />} />
          <Route path="/match/:id" element={<MatchView />} />
          <Route path="/backtest" element={<BacktestPage />} />
          <Route path="/players" element={<LeaderboardPage />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </motion.div>
    </AnimatePresence>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <MotionConfig reducedMotion="user">
      <AnimatedRoutes />
      <SearchPalette />
      <PlayerDrawer />
      </MotionConfig>
    </BrowserRouter>
  );
}
