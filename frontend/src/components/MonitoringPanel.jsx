import { useEffect, useState } from "react";

// Monitoring dashboard: system health, fit-score distribution, per-league
// fairness audit, coverage, and data freshness — the worksheet's
// "Monitoring" quadrant, computed by GET /monitoring from logged searches.
export default function MonitoringPanel({ apiBase }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  const load = () =>
    fetch(`${apiBase}/monitoring`)
      .then((r) => {
        if (!r.ok) throw new Error(`monitoring failed (${r.status})`);
        return r.json();
      })
      .then((body) => {
        setData(body);
        setError(null);
      })
      .catch((e) => setError(e.message));

  useEffect(() => {
    load();
  }, []);

  if (error)
    return (
      <p className="mt-6 text-sm" style={{ color: "var(--status-critical)" }}>
        {error}
      </p>
    );
  if (!data)
    return (
      <p className="mt-6 text-sm" style={{ color: "var(--text-muted)" }}>
        Loading metrics…
      </p>
    );

  const { system_health: sys, data_freshness: fresh, coverage } = data;
  const { buckets, counts } = data.fit_score_distribution;
  const maxCount = Math.max(...counts, 1);

  const tiles = [
    { label: "Searches logged", value: sys.searches_logged },
    {
      label: "Avg response",
      value: sys.avg_response_ms != null ? `${sys.avg_response_ms} ms` : "—",
      note: "target < 5000 ms",
      good: sys.avg_response_ms != null && sys.avg_response_ms < 5000,
    },
    {
      label: "P95 response",
      value: sys.p95_response_ms != null ? `${sys.p95_response_ms} ms` : "—",
      good: sys.p95_response_ms != null && sys.p95_response_ms < 5000,
    },
    {
      label: "Coverage",
      value: `${coverage.coverage_rate_pct}%`,
      note: `${coverage.distinct_players_recommended} of ${coverage.eligible_pool} eligible players recommended`,
    },
  ];

  return (
    <div className="mt-6 space-y-6">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {tiles.map((tile) => (
          <div
            key={tile.label}
            className="rounded-xl border p-4"
            style={{ background: "var(--surface-1)", borderColor: "var(--hairline)" }}
          >
            <p className="text-xs" style={{ color: "var(--text-muted)" }}>
              {tile.label}
            </p>
            <p className="mt-1 text-2xl font-semibold">
              {tile.value}
              {tile.good && (
                <span
                  className="ml-2 align-middle text-xs font-medium"
                  style={{ color: "var(--status-good)" }}
                >
                  ✓ on target
                </span>
              )}
            </p>
            {tile.note && (
              <p className="mt-1 text-[11px]" style={{ color: "var(--text-muted)" }}>
                {tile.note}
              </p>
            )}
          </div>
        ))}
      </div>

      <div
        className="rounded-xl border p-4"
        style={{ background: "var(--surface-1)", borderColor: "var(--hairline)" }}
      >
        <h3 className="text-sm font-semibold">Fit score distribution</h3>
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>
          Across all logged recommendations — tight clustering means the model
          isn't differentiating.
        </p>
        <div className="mt-3 flex h-32 items-end gap-1.5">
          {counts.map((count, i) => (
            <div key={buckets[i]} className="flex-1 text-center">
              <div
                className="mx-auto w-full rounded-t"
                title={`${buckets[i]}: ${count}`}
                style={{
                  height: `${(count / maxCount) * 100}%`,
                  minHeight: count > 0 ? "3px" : "0",
                  background: "var(--series-1)",
                }}
              />
            </div>
          ))}
        </div>
        <div
          className="mt-1 flex gap-1.5 text-[10px]"
          style={{ color: "var(--text-muted)" }}
        >
          {buckets.map((b) => (
            <span key={b} className="flex-1 text-center">
              {b.split("-")[0]}
            </span>
          ))}
        </div>
      </div>

      <div
        className="rounded-xl border p-4"
        style={{ background: "var(--surface-1)", borderColor: "var(--hairline)" }}
      >
        <h3 className="text-sm font-semibold">Fairness by league</h3>
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>
          A league whose appearance share sits far below its pool share is
          being systematically under-recommended.
        </p>
        <table className="mt-3 w-full text-xs">
          <thead>
            <tr style={{ color: "var(--text-muted)" }}>
              <th className="py-1 text-left font-medium">League</th>
              <th className="py-1 text-right font-medium">Eligible</th>
              <th className="py-1 text-right font-medium">Pool share</th>
              <th className="py-1 text-right font-medium">Appearance share</th>
              <th className="py-1 text-right font-medium">Avg fit</th>
            </tr>
          </thead>
          <tbody>
            {data.fairness_by_league.map((row) => (
              <tr
                key={row.league}
                className="border-t"
                style={{ borderColor: "var(--hairline)" }}
              >
                <td className="py-1.5">{row.league}</td>
                <td className="py-1.5 text-right tabular-nums">
                  {row.eligible_players}
                </td>
                <td className="py-1.5 text-right tabular-nums">
                  {row.pool_share_pct}%
                </td>
                <td className="py-1.5 text-right tabular-nums">
                  {row.appearance_share_pct}%
                  {row.appearance_share_pct === 0 && (
                    <span
                      className="ml-1.5 font-medium"
                      style={{ color: "var(--status-critical)" }}
                    >
                      ⚠ never appears
                    </span>
                  )}
                </td>
                <td className="py-1.5 text-right tabular-nums">
                  {row.avg_fit_score ?? "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div
        className="rounded-xl border p-4"
        style={{ background: "var(--surface-1)", borderColor: "var(--hairline)" }}
      >
        <h3 className="text-sm font-semibold">Data freshness</h3>
        <p className="mt-2 text-xs" style={{ color: "var(--text-secondary)" }}>
          {fresh.players_total} players in database ·{" "}
          {fresh.players_with_market_value} with market values ·{" "}
          {fresh.eligible_pool} eligible (valued, 450+ min) · last pipeline
          run:{" "}
          {fresh.last_pipeline_run
            ? new Date(fresh.last_pipeline_run).toLocaleString()
            : "unknown"}
        </p>
        <p className="mt-1 text-xs" style={{ color: "var(--text-muted)" }}>
          {Object.entries(fresh.players_by_position)
            .map(([pos, n]) => `${pos}: ${n}`)
            .join(" · ")}
        </p>
      </div>

      <button
        onClick={load}
        className="rounded-md border px-3 py-1.5 text-xs font-medium"
        style={{ borderColor: "var(--hairline)" }}
      >
        Refresh metrics
      </button>
    </div>
  );
}
