import { FEATURE_LABELS } from "../App.jsx";

// Categorical slots 1-3 from the palette (light/dark handled via CSS vars
// for slot 1; green is mode-invariant; magenta uses the light step — all
// three are direct-labelled in the legend and table, never colour-alone).
const SERIES_COLORS = ["var(--series-1)", "#008300", "#d55181"];

const SIZE = 300;
const CENTER = SIZE / 2;
const RADIUS = 105;

// Map one player's breakdown to radar points using percentile-in-pool as
// the shared 0-1 axis scale (raw units differ per feature).
function polygonPoints(breakdown, key) {
  const n = breakdown.length;
  return breakdown
    .map((item, i) => {
      const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
      const r = RADIUS * Math.max(0.02, item[key]);
      return `${CENTER + r * Math.cos(angle)},${CENTER + r * Math.sin(angle)}`;
    })
    .join(" ");
}

// Side-by-side comparison of 2-3 shortlisted players: an overlaid radar
// chart (axes = the position's features, scale = percentile within the
// affordable candidate pool) plus the raw numbers underneath.
export default function ComparePanel({ players, onClear }) {
  const breakdownRef = players[0].breakdown;
  const n = breakdownRef.length;

  const axisLabel = (i) => {
    const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
    const r = RADIUS + 18;
    const x = CENTER + r * Math.cos(angle);
    const y = CENTER + r * Math.sin(angle);
    const anchor =
      Math.abs(Math.cos(angle)) < 0.3 ? "middle" : Math.cos(angle) > 0 ? "start" : "end";
    return { x, y, anchor };
  };

  return (
    <section
      className="mt-6 rounded-xl border p-4"
      style={{ background: "var(--surface-1)", borderColor: "var(--hairline)" }}
    >
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-base font-semibold">Compare</h2>
          <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
            Axes show each player's percentile among affordable candidates;
            the dashed outline is your ideal profile.
          </p>
        </div>
        <button
          onClick={onClear}
          className="text-xs underline"
          style={{ color: "var(--text-muted)" }}
        >
          Clear
        </button>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-8">
        <svg
          width={SIZE + 130}
          height={SIZE}
          viewBox={`-65 0 ${SIZE + 130} ${SIZE}`}
          role="img"
          aria-label="Radar chart comparing selected players"
        >
          {[0.25, 0.5, 0.75, 1].map((ring) => (
            <polygon
              key={ring}
              points={polygonPoints(
                breakdownRef.map(() => ({ v: ring })),
                "v"
              )}
              fill="none"
              stroke="var(--hairline)"
              strokeWidth="1"
            />
          ))}
          {breakdownRef.map((_, i) => {
            const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
            return (
              <line
                key={i}
                x1={CENTER}
                y1={CENTER}
                x2={CENTER + RADIUS * Math.cos(angle)}
                y2={CENTER + RADIUS * Math.sin(angle)}
                stroke="var(--hairline)"
                strokeWidth="1"
              />
            );
          })}

          <polygon
            points={polygonPoints(breakdownRef, "ideal_percentile")}
            fill="none"
            stroke="var(--benchmark)"
            strokeWidth="2"
            strokeDasharray="5 4"
          />
          {players.map((player, pi) => (
            <polygon
              key={player.name}
              points={polygonPoints(player.breakdown, "player_percentile")}
              fill={SERIES_COLORS[pi]}
              fillOpacity="0.08"
              stroke={SERIES_COLORS[pi]}
              strokeWidth="2"
            />
          ))}

          {breakdownRef.map((item, i) => {
            const { x, y, anchor } = axisLabel(i);
            return (
              <text
                key={item.feature}
                x={x}
                y={y}
                textAnchor={anchor}
                dominantBaseline="middle"
                fontSize="10"
                fill="var(--text-muted)"
              >
                {FEATURE_LABELS[item.feature]}
              </text>
            );
          })}
        </svg>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap gap-4 text-xs">
            {players.map((player, pi) => (
              <span key={player.name} className="flex items-center gap-1.5">
                <span
                  className="inline-block h-2.5 w-2.5 rounded-full"
                  style={{ background: SERIES_COLORS[pi] }}
                />
                {player.name} ({player.fit_score})
              </span>
            ))}
            <span className="flex items-center gap-1.5" style={{ color: "var(--text-muted)" }}>
              <span
                className="inline-block h-0.5 w-4"
                style={{ borderTop: "2px dashed var(--benchmark)" }}
              />
              Ideal
            </span>
          </div>

          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr style={{ color: "var(--text-muted)" }}>
                  <th className="py-1 pr-3 text-left font-medium">Stat</th>
                  {players.map((p) => (
                    <th key={p.name} className="py-1 pr-3 text-right font-medium">
                      {p.name.split(" ").slice(-1)[0]}
                    </th>
                  ))}
                  <th className="py-1 text-right font-medium">Ideal</th>
                </tr>
              </thead>
              <tbody>
                {breakdownRef.map((item, fi) => (
                  <tr
                    key={item.feature}
                    className="border-t"
                    style={{ borderColor: "var(--hairline)" }}
                  >
                    <td className="py-1 pr-3" style={{ color: "var(--text-secondary)" }}>
                      {FEATURE_LABELS[item.feature]}
                    </td>
                    {players.map((p) => (
                      <td key={p.name} className="py-1 pr-3 text-right tabular-nums">
                        {p.breakdown[fi].player_value}
                      </td>
                    ))}
                    <td
                      className="py-1 text-right tabular-nums"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {item.ideal_value}
                    </td>
                  </tr>
                ))}
                <tr className="border-t" style={{ borderColor: "var(--hairline)" }}>
                  <td className="py-1 pr-3" style={{ color: "var(--text-secondary)" }}>
                    Market value
                  </td>
                  {players.map((p) => (
                    <td key={p.name} className="py-1 pr-3 text-right tabular-nums">
                      €{(p.market_value_eur / 1e6).toFixed(1)}m
                    </td>
                  ))}
                  <td className="py-1 text-right" style={{ color: "var(--text-muted)" }}>
                    —
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </section>
  );
}
