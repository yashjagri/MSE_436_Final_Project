import FeatureBar from "./FeatureBar.jsx";
import { FEATURE_LABELS } from "../App.jsx";

// Fit-score badge colours: green above 80, amber 60-80, red below 60.
const badgeStyle = (score) => {
  if (score > 80) return { background: "var(--status-good)", color: "#fff" };
  if (score >= 60) return { background: "var(--status-warning)", color: "#0b0b0b" };
  return { background: "var(--status-critical)", color: "#fff" };
};

const formatMarketValue = (eur) =>
  eur == null ? "—" : `€${(eur / 1_000_000).toFixed(1)}m`;

// One shortlist entry: identity line, fit badge, and the player-vs-ideal
// feature comparison bars.
export default function PlayerCard({ player, rank }) {
  return (
    <div
      className="rounded-xl border p-4"
      style={{ background: "var(--surface-1)", borderColor: "var(--hairline)" }}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs" style={{ color: "var(--text-muted)" }}>
            #{rank}
          </p>
          <h3 className="text-base font-semibold">{player.name}</h3>
          <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
            {player.position} · {player.league} · {player.age} yrs ·{" "}
            {formatMarketValue(player.market_value_eur)}
          </p>
        </div>
        <span
          className="rounded-full px-2.5 py-1 text-xs font-bold"
          style={badgeStyle(player.fit_score)}
          title="Fit score out of 100"
        >
          {player.fit_score}
        </span>
      </div>

      <div className="mt-4 space-y-3">
        {player.breakdown.map((item) => (
          <FeatureBar
            key={item.feature}
            label={FEATURE_LABELS[item.feature] ?? item.feature}
            playerValue={item.player_value}
            idealValue={item.ideal_value}
          />
        ))}
      </div>

      <div
        className="mt-3 flex gap-4 border-t pt-2 text-[11px]"
        style={{ borderColor: "var(--hairline)", color: "var(--text-muted)" }}
      >
        <span className="flex items-center gap-1.5">
          <span
            className="inline-block h-2 w-2 rounded-full"
            style={{ background: "var(--series-1)" }}
          />
          Player
        </span>
        <span className="flex items-center gap-1.5">
          <span
            className="inline-block h-2 w-2 rounded-full"
            style={{ background: "var(--benchmark)" }}
          />
          Ideal
        </span>
      </div>
    </div>
  );
}
