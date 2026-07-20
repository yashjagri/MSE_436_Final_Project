import { DECISIONS, DECISION_COLOR } from "../App.jsx";

const formatMarketValue = (eur) =>
  eur == null ? "—" : `€${(eur / 1_000_000).toFixed(1)}m`;

// The recruitment decision log: every player the director has acted on,
// grouped by verdict. This is the system's memory across sessions — the
// difference between a search tool and a decision-support system.
export default function DecisionsPanel({ decisions, onDecide, onRefresh }) {
  if (!decisions.length) {
    return (
      <p className="mt-10 text-sm" style={{ color: "var(--text-muted)" }}>
        No decisions yet. On the shortlist, mark players as Pursue, Pass, or
        Signed and they will collect here.
      </p>
    );
  }

  // A minimal player-shaped object so onDecide (which expects join_key etc.)
  // works from the log the same way it does from a shortlist card.
  const asPlayer = (d) => ({
    join_key: d.join_key,
    name: d.player_name,
    position: d.position,
    league: d.league,
    market_value_eur: d.market_value_eur,
    fit_score: d.fit_score,
  });

  const exportCsv = () => {
    const header = ["status", "player", "position", "league",
      "market_value_eur", "fit_score", "note", "updated_at"];
    const rows = decisions.map((d) => [
      d.status, d.player_name, d.position, d.league, d.market_value_eur,
      d.fit_score, d.note ?? "", d.updated_at,
    ]);
    const csv = [header, ...rows]
      .map((row) => row.map((v) => `"${String(v ?? "").replace(/"/g, '""')}"`).join(","))
      .join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "recruitment_decisions.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="mt-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Recruitment decisions</h1>
          <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
            {decisions.length} player{decisions.length === 1 ? "" : "s"} tracked
            across all searches.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={onRefresh}
            className="rounded-md border px-3 py-1.5 text-sm font-medium"
            style={{ borderColor: "var(--hairline)" }}
          >
            Refresh
          </button>
          <button
            onClick={exportCsv}
            className="rounded-md border px-3 py-1.5 text-sm font-medium"
            style={{ borderColor: "var(--hairline)" }}
          >
            Export CSV
          </button>
        </div>
      </div>

      {DECISIONS.map((d) => {
        const group = decisions.filter((x) => x.status === d.key);
        if (!group.length) return null;
        return (
          <section key={d.key} className="mt-6">
            <h2
              className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide"
              style={{ color: "var(--text-secondary)" }}
            >
              <span
                className="inline-block h-2.5 w-2.5 rounded-full"
                style={{ background: d.color }}
              />
              {d.label} ({group.length})
            </h2>
            <div className="mt-2 overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr
                    className="text-left text-xs"
                    style={{ color: "var(--text-muted)" }}
                  >
                    <th className="py-1 pr-4 font-medium">Player</th>
                    <th className="py-1 pr-4 font-medium">Position</th>
                    <th className="py-1 pr-4 font-medium">League</th>
                    <th className="py-1 pr-4 font-medium">Value</th>
                    <th className="py-1 pr-4 font-medium">Fit</th>
                    <th className="py-1 pr-4 font-medium">Move to</th>
                  </tr>
                </thead>
                <tbody>
                  {group.map((row) => (
                    <tr
                      key={row.join_key}
                      className="border-t"
                      style={{ borderColor: "var(--hairline)" }}
                    >
                      <td className="py-1.5 pr-4 font-medium">{row.player_name}</td>
                      <td className="py-1.5 pr-4" style={{ color: "var(--text-secondary)" }}>
                        {row.position ?? "—"}
                      </td>
                      <td className="py-1.5 pr-4" style={{ color: "var(--text-secondary)" }}>
                        {row.league ?? "—"}
                      </td>
                      <td className="py-1.5 pr-4" style={{ color: "var(--text-secondary)" }}>
                        {formatMarketValue(row.market_value_eur)}
                      </td>
                      <td className="py-1.5 pr-4" style={{ color: "var(--text-secondary)" }}>
                        {row.fit_score ?? "—"}
                      </td>
                      <td className="py-1.5 pr-4">
                        <div className="flex gap-1">
                          {DECISIONS.filter((o) => o.key !== row.status).map((o) => (
                            <button
                              key={o.key}
                              onClick={() => onDecide(asPlayer(row), o.key)}
                              className="rounded border px-1.5 py-0.5 text-[11px]"
                              style={{
                                borderColor: "var(--hairline)",
                                color: DECISION_COLOR[o.key],
                              }}
                            >
                              {o.label}
                            </button>
                          ))}
                          <button
                            onClick={() => onDecide(asPlayer(row), row.status)}
                            className="rounded border px-1.5 py-0.5 text-[11px]"
                            style={{
                              borderColor: "var(--hairline)",
                              color: "var(--text-muted)",
                            }}
                            title="Remove from the decision log"
                          >
                            Clear
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        );
      })}
    </div>
  );
}
