import { useState } from "react";
import Sidebar from "./components/Sidebar.jsx";
import PlayerCard from "./components/PlayerCard.jsx";

const API_BASE = "http://localhost:8000";

export const POSITIONS = [
  "Goalkeeper",
  "Fullback",
  "Centre Back",
  "Midfielder",
  "Winger",
  "Striker",
];

// Features the KNN model uses per position (must match model/knn.py).
export const POSITION_FEATURES = {
  Goalkeeper: ["save_pct", "clean_sheets_per90", "saves", "pass_completion_pct"],
  Fullback: ["tackles_won_per90", "interceptions_per90", "key_passes_per90", "passes_per90"],
  "Centre Back": ["aerial_duels_won_pct", "tackles_won_per90", "interceptions_per90", "pass_completion_pct"],
  Midfielder: ["passes_per90", "key_passes_per90", "interceptions_per90", "successful_dribbles_per90"],
  Winger: ["successful_dribbles_per90", "goals_per90", "key_passes_per90", "shots_per90"],
  Striker: ["goals_per90", "shots_per90", "shots_on_target_pct", "aerial_duels_won_pct"],
};

export const FEATURE_LABELS = {
  save_pct: "Save %",
  clean_sheets_per90: "Clean sheets per 90",
  saves: "Saves",
  pass_completion_pct: "Pass completion %",
  tackles_won_per90: "Tackles won per 90",
  interceptions_per90: "Interceptions per 90",
  key_passes_per90: "Key passes per 90",
  passes_per90: "Passes per 90",
  aerial_duels_won_pct: "Aerial duels won %",
  successful_dribbles_per90: "Successful dribbles per 90",
  goals_per90: "Goals per 90",
  shots_per90: "Shots per 90",
  shots_on_target_pct: "Shots on target %",
};

const defaultWeights = (position) =>
  Object.fromEntries(POSITION_FEATURES[position].map((f) => [f, 1]));

export default function App() {
  const [position, setPosition] = useState("Striker");
  const [budgetM, setBudgetM] = useState(50);
  const [ageRange, setAgeRange] = useState([18, 32]);
  const [weights, setWeights] = useState(defaultWeights("Striker"));
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handlePositionChange = (next) => {
    setPosition(next);
    setWeights(defaultWeights(next));
    // Old results are for a different position; clear rather than mislead.
    setResults(null);
    setError(null);
  };

  const handleSearch = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/recommend`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          position,
          max_budget_eur: budgetM * 1_000_000,
          min_age: ageRange[0],
          max_age: ageRange[1],
          weights,
        }),
      });
      const body = await response.json();
      if (!response.ok) {
        const detail =
          typeof body.detail === "string"
            ? body.detail
            : "The request was rejected — check your inputs.";
        throw new Error(detail);
      }
      setResults(body.results ?? []);
    } catch (err) {
      setError(err.message);
      setResults(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen">
      <Sidebar
        position={position}
        onPositionChange={handlePositionChange}
        budgetM={budgetM}
        onBudgetChange={setBudgetM}
        ageRange={ageRange}
        onAgeRangeChange={setAgeRange}
        weights={weights}
        onWeightsChange={setWeights}
        onSearch={handleSearch}
        loading={loading}
      />

      <main className="flex-1 p-6">
        <h1 className="text-xl font-semibold">Transfer shortlist</h1>
        <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
          Ranked by KNN fit against your ideal {position.toLowerCase()} profile.
        </p>

        {loading && (
          <p className="mt-10 text-sm" style={{ color: "var(--text-muted)" }}>
            Scoring players…
          </p>
        )}

        {error && !loading && (
          <div
            className="mt-6 rounded-lg border p-4 text-sm"
            style={{ borderColor: "var(--status-critical)" }}
          >
            {error}
          </div>
        )}

        {!loading && !error && results === null && (
          <p className="mt-10 text-sm" style={{ color: "var(--text-muted)" }}>
            Set your requirements in the sidebar and press Search.
          </p>
        )}

        {!loading && !error && results !== null && results.length === 0 && (
          <p className="mt-10 text-sm" style={{ color: "var(--text-muted)" }}>
            No players matched these requirements. Try a higher budget or a
            wider age range.
          </p>
        )}

        {!loading && results && results.length > 0 && (
          <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-2 2xl:grid-cols-3">
            {results.map((player, rank) => (
              <PlayerCard key={player.name} player={player} rank={rank + 1} />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
