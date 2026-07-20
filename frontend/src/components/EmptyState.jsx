import { LEAGUES } from "../App.jsx";

// Shown when the brief matches too few players (the API's 422) or an empty
// pool. Instead of a dead-end error, it offers one-click fixes that loosen
// whichever filters are actually constraining the search.
export default function EmptyState({
  message,
  budgetM,
  onBudgetChange,
  ageRange,
  onAgeRangeChange,
  minMinutes,
  onMinMinutesChange,
  leagues,
  onLeaguesChange,
}) {
  const [minAge, maxAge] = ageRange;

  // Each candidate fix is offered only when it can actually widen the pool.
  const fixes = [];
  if (budgetM < 200) {
    const next = Math.min(200, budgetM + 25);
    fixes.push({
      label: `Raise budget to €${next}m`,
      onClick: () => onBudgetChange(next),
    });
  }
  if (minAge > 16 || maxAge < 34) {
    fixes.push({
      label: `Widen age to ${Math.min(minAge, 18)}–${Math.max(maxAge, 34)}`,
      onClick: () =>
        onAgeRangeChange([Math.min(minAge, 18), Math.max(maxAge, 34)]),
    });
  }
  if (minMinutes > 0) {
    const next = Math.max(0, minMinutes - 250);
    fixes.push({
      label:
        next === 0 ? "Drop the minutes filter" : `Lower minutes to ${next}`,
      onClick: () => onMinMinutesChange(next),
    });
  }
  if (leagues.length < LEAGUES.length) {
    fixes.push({
      label: "Include all leagues",
      onClick: () => onLeaguesChange([...LEAGUES]),
    });
  }

  return (
    <div
      className="mt-6 rounded-xl border p-6"
      style={{ background: "var(--surface-1)", borderColor: "var(--hairline)" }}
    >
      <h2 className="text-base font-semibold">Not enough matches</h2>
      <p className="mt-1 text-sm" style={{ color: "var(--text-secondary)" }}>
        {message ||
          "No players matched these requirements. Loosen a filter to widen the pool."}
      </p>

      {fixes.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {fixes.map((fix) => (
            <button
              key={fix.label}
              onClick={fix.onClick}
              className="rounded-md border px-3 py-1.5 text-sm font-medium transition-colors"
              style={{ borderColor: "var(--series-1)", color: "var(--series-1)" }}
            >
              {fix.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
