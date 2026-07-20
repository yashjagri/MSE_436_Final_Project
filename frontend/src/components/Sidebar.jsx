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
  const AGE_MIN = 15;
  const AGE_MAX = 40;
  const pct = (v) => ((v - AGE_MIN) / (AGE_MAX - AGE_MIN)) * 100;

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
        {/* Dual-thumb slider: two range inputs stacked on one track, with a
            filled band between the thumbs so the selected range reads at a
            glance. Thumbs stay clickable via pointer-events toggling. */}
        <div className="dual-range relative mt-3 h-5">
          <div
            className="absolute top-1/2 h-1 w-full -translate-y-1/2 rounded-full"
            style={{ background: "var(--hairline)" }}
          />
          <div
            className="absolute top-1/2 h-1 -translate-y-1/2 rounded-full"
            style={{
              left: `${pct(minAge)}%`,
              right: `${100 - pct(maxAge)}%`,
              background: "var(--series-1)",
            }}
          />
          <input
            type="range"
            min={AGE_MIN}
            max={AGE_MAX}
            value={minAge}
            aria-label="Minimum age"
            onChange={(e) =>
              onAgeRangeChange([
                Math.min(Number(e.target.value), maxAge),
                maxAge,
              ])
            }
          />
          <input
            type="range"
            min={AGE_MIN}
            max={AGE_MAX}
            value={maxAge}
            aria-label="Maximum age"
            onChange={(e) =>
              onAgeRangeChange([
                minAge,
                Math.max(Number(e.target.value), minAge),
              ])
            }
          />
        </div>
        <div
          className="mt-1 flex justify-between text-[10px]"
          style={{ color: "var(--text-muted)" }}
        >
          <span>{AGE_MIN}</span>
          <span>{AGE_MAX}</span>
        </div>
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
