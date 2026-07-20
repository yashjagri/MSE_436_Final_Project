import { useEffect, useState } from "react";

const formatMarketValue = (eur) =>
  eur == null ? "—" : `€${(eur / 1_000_000).toFixed(1)}m`;

// Colour a recall lift: >1 (better than chance) reads positive, <1 negative.
const liftColor = (lift) =>
  lift == null
    ? "var(--text-muted)"
    : lift >= 1
      ? "var(--status-good)"
      : "var(--status-critical)";

// Impact-simulation view: replays real 2024/25 -> 2025/26 transfers and shows
// how the model's fit ranking lines up with players clubs actually signed.
export default function BacktestPanel({ apiBase }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch(`${apiBase}/backtest`)
      .then(async (r) => {
        const body = await r.json();
        if (!r.ok) throw new Error(body.detail ?? "Failed to load backtest.");
        return body;
      })
      .then(setData)
      .catch((e) => setError(e.message));
  }, [apiBase]);

  if (error) {
    return (
      <p className="mt-10 text-sm" style={{ color: "var(--text-muted)" }}>
        {error}
      </p>
    );
  }
  if (!data) {
    return (
      <p className="mt-10 text-sm" style={{ color: "var(--text-muted)" }}>
        Loading backtest…
      </p>
    );
  }
  if (!data.overall) {
    return (
      <p className="mt-10 text-sm" style={{ color: "var(--text-muted)" }}>
        {data.note ?? "No transfers evaluated yet."}
      </p>
    );
  }

  const o = data.overall;
  const stat = (label, value, sub) => (
    <div
      className="rounded-xl border p-4"
      style={{ background: "var(--surface-1)", borderColor: "var(--hairline)" }}
    >
      <p className="text-xs" style={{ color: "var(--text-muted)" }}>{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
      {sub && (
        <p className="text-xs" style={{ color: "var(--text-secondary)" }}>{sub}</p>
      )}
    </div>
  );

  return (
    <div className="mt-4">
      <h1 className="text-xl font-semibold">Transfer backtest</h1>
      <p className="mt-1 max-w-3xl text-sm" style={{ color: "var(--text-secondary)" }}>
        We replay every real move between the {data.prior_season} and{" "}
        {data.current_season} seasons ({data.transfers_detected} detected) and
        ask: using only the {data.prior_season} stats a director had at the
        time, does the model rank the player who was actually signed among the
        top 15 for their position and price? Recall is shown against the
        random-shortlist baseline, so a lift above 1× means the model beats
        chance.
      </p>

      <div className="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
        {stat("Signings evaluated", o.evaluated,
          `of ${data.transfers_detected} detected`)}
        {stat("Median fit percentile", `${Math.round(o.median_fit_percentile * 100)}%`,
          "50% = average player")}
        {stat("Top-15 recall", `${o.top15_recall_pct}%`,
          `${o.random_recall_pct}% by chance`)}
        {stat("Recall lift", o.recall_lift != null ? `${o.recall_lift}×` : "—",
          o.recall_lift >= 1 ? "beats chance" : "below chance")}
      </div>

      <h2 className="mt-8 text-sm font-semibold uppercase tracking-wide"
        style={{ color: "var(--text-secondary)" }}>
        By position
      </h2>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs" style={{ color: "var(--text-muted)" }}>
              <th className="py-1 pr-4 font-medium">Position</th>
              <th className="py-1 pr-4 font-medium">Signings</th>
              <th className="py-1 pr-4 font-medium">Recall</th>
              <th className="py-1 pr-4 font-medium">Random</th>
              <th className="py-1 pr-4 font-medium">Lift</th>
              <th className="py-1 pr-4 font-medium">Median pctile</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(data.by_position)
              .sort((a, b) => b[1].evaluated - a[1].evaluated)
              .map(([pos, s]) => (
                <tr key={pos} className="border-t" style={{ borderColor: "var(--hairline)" }}>
                  <td className="py-1.5 pr-4 font-medium">{pos}</td>
                  <td className="py-1.5 pr-4" style={{ color: "var(--text-secondary)" }}>
                    {s.evaluated}
                  </td>
                  <td className="py-1.5 pr-4" style={{ color: "var(--text-secondary)" }}>
                    {s.top15_recall_pct}%
                  </td>
                  <td className="py-1.5 pr-4" style={{ color: "var(--text-muted)" }}>
                    {s.random_recall_pct}%
                  </td>
                  <td className="py-1.5 pr-4 font-semibold"
                    style={{ color: liftColor(s.recall_lift) }}>
                    {s.recall_lift != null ? `${s.recall_lift}×` : "—"}
                  </td>
                  <td className="py-1.5 pr-4" style={{ color: "var(--text-secondary)" }}>
                    {Math.round(s.median_fit_percentile * 100)}%
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-2">
        <BestWorst title="Best-rated real signings" rows={data.best_fits} />
        <BestWorst title="Signings the model would have missed" rows={data.worst_fits} />
      </div>

      <p className="mt-6 max-w-3xl text-xs" style={{ color: "var(--text-muted)" }}>
        Caveat: only signings whose {data.prior_season} stats are in the
        database are scored, so coverage grows as more leagues load. Attacking
        roles show the strongest signal because their value (goals, dribbles,
        key passes) is directly measured; midfield and defensive value depends
        on qualities the free-tier stats capture less well.
      </p>
    </div>
  );
}

function BestWorst({ title, rows }) {
  return (
    <div>
      <h2 className="text-sm font-semibold uppercase tracking-wide"
        style={{ color: "var(--text-secondary)" }}>
        {title}
      </h2>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs" style={{ color: "var(--text-muted)" }}>
              <th className="py-1 pr-3 font-medium">Player</th>
              <th className="py-1 pr-3 font-medium">Move</th>
              <th className="py-1 pr-3 font-medium">Value</th>
              <th className="py-1 pr-3 font-medium">Pctile</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.name} className="border-t" style={{ borderColor: "var(--hairline)" }}>
                <td className="py-1.5 pr-3 font-medium">{r.name}</td>
                <td className="py-1.5 pr-3 text-xs" style={{ color: "var(--text-secondary)" }}>
                  {r.from_club} → {r.to_club}
                </td>
                <td className="py-1.5 pr-3" style={{ color: "var(--text-secondary)" }}>
                  {formatMarketValue(r.market_value_eur)}
                </td>
                <td className="py-1.5 pr-3" style={{ color: "var(--text-secondary)" }}>
                  {Math.round(r.fit_percentile * 100)}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
