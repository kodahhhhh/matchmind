import { BrowserRouter, Route, Routes } from "react-router";
import { MatchBrowser } from "./components/browser/MatchBrowser";
import { MatchView } from "./components/match/MatchView";
import { SearchPalette } from "./components/search/SearchPalette";
import { BacktestPage } from "./components/backtest/BacktestPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<MatchBrowser />} />
        <Route path="/match/:id" element={<MatchView />} />
        <Route path="/backtest" element={<BacktestPage />} />
      </Routes>
      <SearchPalette />
    </BrowserRouter>
  );
}
