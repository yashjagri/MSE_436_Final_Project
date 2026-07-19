import { POSITIONS, LEAGUES, POSITION_FEATURES, FEATURE_LABELS } from "../App.jsx";

// Left control panel: position, budget, age range, minutes, leagues, and
// per-feature weights. Every change re-runs the search automatically
// (debounced in App); the button is an explicit "run now".
export default function Sidebar({
  position,
  onPositionChange,
  budgetM,
  onBudgetChange,
  ageRange,
  onAgeRangeChange,
  minMinutes,
  onMinMinutesChange,
  leagues,
  onLeaguesChange,
  weights,
  onWeightsChange,
  onSearch,
  loading,
}) {
  const [minAge, maxAge] = ageRange;

  const setWeight = (feature, value) =>
    onWeightsChange({ ...weights, [feature]: value });

  const toggleLeague = (league) => {
    const next = leagues.includes(league)
      ? leagues.filter((l) => l !== league)
      : [...leagues, league];
    if (next.length > 0) onLeaguesChange(next); // never allow zero leagues
  };

  return (
    <aside
      className="w-80 shrink-0 border-r p-6"
      style={{ background: "var(--surface-1)", borderColor: "var(--hairline)" }}
    >
      <h2 className="text-lg font-semibold">Requirements</h2>
      <p className="mt-1 text-xs" style={{ color: "var(--text-muted)" }}>
        The shortlist updates as you adjust.
      </p>

      <label className="mt-5 block text-sm font-medium">
        Position
        <select
          value={position}
          onChange={(e) => onPositionChange(e.target.value)}
          className="mt-1 w-full rounded-md border px-2 py-1.5 text-sm"
          style={{ borderColor: "var(--hairline)", background: "var(--page)" }}
        >
          {POSITIONS.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
      </label>

      <label className="mt-5 block text-sm font-medium">
        Budget: €{budgetM}m
        <input
          type="range"
          min="0"
          max="200"
          step="1"
          value={budgetM}
          onChange={(e) => onBudgetChange(Number(e.target.value))}
          className="mt-1 w-full"
        />
      </label>

      <fieldset className="mt-5">
        <legend className="text-sm font-medium">
          Age range: {minAge}–{maxAge}
        </legend>
        <label className="mt-1 block text-xs" style={{ color: "var(--text-secondary)" }}>
          Minimum age
          <input
            type="range"
            min="15"
            max="40"
            value={minAge}
            onChange={(e) =>
              onAgeRangeChange([
                Math.min(Number(e.target.value), maxAge),
                maxAge,
              ])
            }
            className="w-full"
          />
        </label>
        <label className="mt-1 block text-xs" style={{ color: "var(--text-secondary)" }}>
          Maximum age
          <input
            type="range"
            min="15"
            max="40"
            value={maxAge}
            onChange={(e) =>
              onAgeRangeChange([
                minAge,
                Math.max(Number(e.target.value), minAge),
              ])
            }
            className="w-full"
          />
        </label>
      </fieldset>

      <label className="mt-5 block text-sm font-medium">
        Minimum minutes: {minMinutes}
        <input
          type="range"
          min="0"
          max="3000"
          step="50"
          value={minMinutes}
          onChange={(e) => onMinMinutesChange(Number(e.target.value))}
          className="mt-1 w-full"
        />
        <span className="text-xs font-normal" style={{ color: "var(--text-muted)" }}>
          Filters out small-sample per-90 noise
        </span>
      </label>

      <fieldset className="mt-5">
        <legend className="text-sm font-medium">Leagues</legend>
        {LEAGUES.map((league) => (
          <label key={league} className="mt-1.5 flex items-center gap-2 text-xs">
            <input
              type="checkbox"
              checked={leagues.includes(league)}
              onChange={() => toggleLeague(league)}
            />
            {league}
          </label>
        ))}
      </fieldset>

      <fieldset className="mt-5">
        <legend className="text-sm font-medium">Attribute priorities</legend>
        <p className="mt-1 text-xs" style={{ color: "var(--text-muted)" }}>
          0 = ignore, 1 = normal, 3 = essential
        </p>
        {POSITION_FEATURES[position].map((feature) => (
          <label key={feature} className="mt-3 block text-xs">
            <span className="flex justify-between">
              <span>{FEATURE_LABELS[feature]}</span>
              <span style={{ color: "var(--text-secondary)" }}>
                {(weights[feature] ?? 1).toFixed(1)}
              </span>
            </span>
            <input
              type="range"
              min="0"
              max="3"
              step="0.1"
              value={weights[feature] ?? 1}
              onChange={(e) => setWeight(feature, Number(e.target.value))}
              className="w-full"
            />
          </label>
        ))}
      </fieldset>

      <button
        onClick={onSearch}
        disabled={loading}
        className="mt-6 w-full rounded-md py-2 text-sm font-semibold text-white disabled:opacity-50"
        style={{ background: "var(--series-1)" }}
      >
        {loading ? "Searching…" : "Search now"}
      </button>
    </aside>
  );
}
