import { BrowserRouter, Route, Routes } from "react-router";
import { MatchBrowser } from "./components/browser/MatchBrowser";
import { MatchView } from "./components/match/MatchView";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<MatchBrowser />} />
        <Route path="/match/:id" element={<MatchView />} />
      </Routes>
    </BrowserRouter>
  );
}
