import { lazy, Suspense } from "react";
import { BrowserRouter, Route, Routes, useLocation } from "react-router";
import { AnimatePresence, MotionConfig, motion } from "motion/react";
import { MatchBrowser } from "./components/browser/MatchBrowser";
import { SearchPalette } from "./components/search/SearchPalette";
import { PlayerDrawer } from "./components/players/PlayerDrawer";
import { NotFound } from "./components/ui/NotFound";

// each screen is its own chunk, so the home page loads only what it shows
const MatchView = lazy(() => import("./components/match/MatchView").then((m) => ({ default: m.MatchView })));
const BacktestPage = lazy(() => import("./components/backtest/BacktestPage").then((m) => ({ default: m.BacktestPage })));
// warm the match screen once the first page has settled: it's where almost every visit goes next
if (typeof window !== "undefined") setTimeout(() => { void import("./components/match/MatchView"); }, 2000);
const LeaderboardPage = lazy(() => import("./components/players/LeaderboardPage").then((m) => ({ default: m.LeaderboardPage })));

function AnimatedRoutes() {
  const location = useLocation();
  // match → match navigation keeps the shell mounted; page-level changes cross-fade
  const key = location.pathname.split("/")[1] || "home";
  return (
    <AnimatePresence mode="wait">
      <motion.div key={key} className="h-full"
        initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, transition: { duration: 0.12, ease: "easeOut" } }}
        transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}>
        <Suspense fallback={<div className="h-full" aria-busy="true" />}>
          <Routes location={location}>
            <Route path="/" element={<MatchBrowser />} />
            <Route path="/match/:id" element={<MatchView />} />
            <Route path="/backtest" element={<BacktestPage />} />
            <Route path="/players" element={<LeaderboardPage />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </Suspense>
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
