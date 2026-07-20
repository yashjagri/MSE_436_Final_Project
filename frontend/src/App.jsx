import { useCallback, useEffect, useRef, useState } from "react";
import Sidebar from "./components/Sidebar.jsx";
import PlayerCard from "./components/PlayerCard.jsx";
import ComparePanel from "./components/ComparePanel.jsx";
import MonitoringPanel from "./components/MonitoringPanel.jsx";
import SkeletonCard from "./components/SkeletonCard.jsx";
import EmptyState from "./components/EmptyState.jsx";

const API_BASE = "http://localhost:8000";

export const POSITIONS = [
  "Goalkeeper",
  "Fullback",
  "Centre Back",
  "Midfielder",
  "Winger",
  "Striker",
];

export const LEAGUES = [
  "Premier League",
  "La Liga",
  "Bundesliga",
  "Serie A",
  "Ligue 1",
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

function exportCsv(results, position) {
  const features = POSITION_FEATURES[position];
  const header = [
    "rank", "name", "position", "league", "age", "market_value_eur",
    "fit_score", "reasons",
    ...features.flatMap((f) => [f, `ideal_${f}`]),
  ];
  const rows = results.map((r, i) => {
    const byFeature = Object.fromEntries(
      r.breakdown.map((b) => [b.feature, b]));
    return [
      i + 1, r.name, r.position, r.league, r.age, r.market_value_eur,
      r.fit_score, (r.reasons ?? []).join("; "),
      ...features.flatMap((f) => [
        byFeature[f]?.player_value ?? "", byFeature[f]?.ideal_value ?? "",
      ]),
    ];
  });
  const csv = [header, ...rows]
    .map((row) => row.map((v) => `"${String(v ?? "").replace(/"/g, '""')}"`).join(","))
    .join("\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = `shortlist_${position.toLowerCase().replace(" ", "_")}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

export default function App() {
  const [view, setView] = useState("shortlist");
  const [position, setPosition] = useState("Striker");
  const [budgetM, setBudgetM] = useState(50);
  const [ageRange, setAgeRange] = useState([18, 32]);
  const [minMinutes, setMinMinutes] = useState(450);
  const [leagues, setLeagues] = useState([...LEAGUES]);
  const [weights, setWeights] = useState(defaultWeights("Striker"));
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [compareNames, setCompareNames] = useState([]);
  const [rankDeltas, setRankDeltas] = useState({});
  const searchSeq = useRef(0);
  // name -> rank (1-based) from the previous shortlist, so we can show how
  // each player moved when a weight or filter changes. null = no baseline yet
  // (first search after mount or a position change), which suppresses badges.
  const prevRankRef = useRef(null);

  const handlePositionChange = (next) => {
    setPosition(next);
    setWeights(defaultWeights(next));
    setCompareNames([]);
    prevRankRef.current = null; // different feature set — deltas aren't comparable
    setRankDeltas({});
  };

  const runSearch = useCallback(async () => {
    const seq = ++searchSeq.current;
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/recommend`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          position,
          max_budget_eur: budgetM * 1_000_000,
          min_age: ageRange[0],
          max_age: ageRange[1],
          min_minutes: minMinutes,
          leagues: leagues.length === LEAGUES.length ? null : leagues,
          weights,
        }),
      });
      const body = await response.json();
      if (seq !== searchSeq.current) return; // a newer search superseded this
      if (!response.ok) {
        const detail =
          typeof body.detail === "string"
            ? body.detail
            : "The request was rejected — check your inputs.";
        // 422 = the brief matched too few players; offer actionable fixes
        // rather than a dead-end error box.
        setError({ message: detail, actionable: response.status === 422 });
        return;
      }
      const next = body.results ?? [];
      // Compare against the previous shortlist to label rank movement.
      const prev = prevRankRef.current;
      if (prev) {
        setRankDeltas(
          Object.fromEntries(
            next.map((p, i) => [
              p.name,
              prev[p.name] == null ? "new" : prev[p.name] - (i + 1),
            ])
          )
        );
      } else {
        setRankDeltas({});
      }
      prevRankRef.current = Object.fromEntries(
        next.map((p, i) => [p.name, i + 1])
      );
      setResults(next);
      setError(null);
    } catch (err) {
      if (seq !== searchSeq.current) return;
      setError({ message: err.message, actionable: false });
    } finally {
      if (seq === searchSeq.current) setLoading(false);
    }
  }, [position, budgetM, ageRange, minMinutes, leagues, weights]);

  // The worksheet's decision rule: the shortlist recomputes whenever any
  // parameter or weight changes (debounced so slider drags don't spam).
  useEffect(() => {
    const timer = setTimeout(runSearch, 400);
    return () => clearTimeout(timer);
  }, [runSearch]);

  const toggleCompare = (name) =>
    setCompareNames((current) =>
      current.includes(name)
        ? current.filter((n) => n !== name)
        : current.length >= 3
          ? current
          : [...current, name]);

  const compared = (results ?? []).filter((r) =>
    compareNames.includes(r.name));

  const tabStyle = (active) => ({
    borderColor: active ? "var(--series-1)" : "transparent",
    color: active ? "var(--text-primary)" : "var(--text-muted)",
  });

  return (
    <div className="flex min-h-screen">
      <Sidebar
        position={position}
        onPositionChange={handlePositionChange}
        budgetM={budgetM}
        onBudgetChange={setBudgetM}
        ageRange={ageRange}
        onAgeRangeChange={setAgeRange}
        minMinutes={minMinutes}
        onMinMinutesChange={setMinMinutes}
        leagues={leagues}
        onLeaguesChange={setLeagues}
        weights={weights}
        onWeightsChange={setWeights}
        onSearch={runSearch}
        loading={loading}
      />

      <main className="flex-1 p-6">
        <div
          className="flex items-center gap-6 border-b"
          style={{ borderColor: "var(--hairline)" }}
        >
          {["shortlist", "monitoring"].map((tab) => (
            <button
              key={tab}
              onClick={() => setView(tab)}
              className="border-b-2 pb-2 text-sm font-semibold capitalize"
              style={tabStyle(view === tab)}
            >
              {tab}
            </button>
          ))}
        </div>

        {view === "monitoring" ? (
          <MonitoringPanel apiBase={API_BASE} />
        ) : (
          <>
            <div className="mt-4 flex items-start justify-between gap-4">
              <div>
                <h1 className="text-xl font-semibold">Transfer shortlist</h1>
                <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
                  Ranked by KNN fit against your ideal{" "}
                  {position.toLowerCase()} profile.
                  {loading && " Updating…"}
                </p>
              </div>
              {results?.length > 0 && (
                <button
                  onClick={() => exportCsv(results, position)}
                  className="rounded-md border px-3 py-1.5 text-sm font-medium"
                  style={{ borderColor: "var(--hairline)" }}
                >
                  Export CSV
                </button>
              )}
            </div>

            {error && !error.actionable && (
              <div
                className="mt-6 rounded-lg border p-4 text-sm"
                style={{ borderColor: "var(--status-critical)" }}
              >
                {error.message}
              </div>
            )}

            {error && error.actionable && (
              <EmptyState
                message={error.message}
                budgetM={budgetM}
                onBudgetChange={setBudgetM}
                ageRange={ageRange}
                onAgeRangeChange={setAgeRange}
                minMinutes={minMinutes}
                onMinMinutesChange={setMinMinutes}
                leagues={leagues}
                onLeaguesChange={setLeagues}
              />
            )}

            {!error && loading && !results?.length && (
              <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-2 2xl:grid-cols-3">
                {Array.from({ length: 6 }).map((_, i) => (
                  <SkeletonCard key={i} />
                ))}
              </div>
            )}

            {!error && !loading && results === null && (
              <p className="mt-10 text-sm" style={{ color: "var(--text-muted)" }}>
                Set your requirements in the sidebar.
              </p>
            )}

            {!error && results !== null && results.length === 0 && (
              <EmptyState
                budgetM={budgetM}
                onBudgetChange={setBudgetM}
                ageRange={ageRange}
                onAgeRangeChange={setAgeRange}
                minMinutes={minMinutes}
                onMinMinutesChange={setMinMinutes}
                leagues={leagues}
                onLeaguesChange={setLeagues}
              />
            )}

            {!error && compared.length >= 2 && (
              <ComparePanel players={compared} onClear={() => setCompareNames([])} />
            )}

            {!error && results?.length > 0 && (
              <div
                className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-2 2xl:grid-cols-3"
                style={{ opacity: loading ? 0.55 : 1 }}
              >
                {results.map((player, rank) => (
                  <PlayerCard
                    key={player.name}
                    player={player}
                    rank={rank + 1}
                    rankDelta={rankDeltas[player.name]}
                    compared={compareNames.includes(player.name)}
                    onToggleCompare={() => toggleCompare(player.name)}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
