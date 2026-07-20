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

// Renders how a player's rank shifted since the last search: ▲/▼ with the
// number of places, or a "new" tag for a player that just entered the list.
// `delta > 0` means the player climbed. Returns null when nothing changed.
function RankDelta({ delta }) {
  if (delta == null || delta === 0) return null;
  if (delta === "new")
    return (
      <span
        className="rounded-full px-1.5 py-0.5 text-[10px] font-semibold"
        style={{ background: "var(--series-1)", color: "#fff" }}
        title="New to the shortlist since your last change"
      >
        new
      </span>
    );
  const up = delta > 0;
  return (
    <span
      className="text-[11px] font-semibold tabular-nums"
      style={{ color: up ? "var(--status-good)" : "var(--status-critical)" }}
      title={`Moved ${up ? "up" : "down"} ${Math.abs(delta)} ${
        Math.abs(delta) === 1 ? "place" : "places"
      } since your last change`}
    >
      {up ? "▲" : "▼"}
      {Math.abs(delta)}
    </span>
  );
}

// One shortlist entry: identity line, fit badge, plain-language reasons,
// and the player-vs-ideal feature comparison bars.
export default function PlayerCard({
  player,
  rank,
  rankDelta,
  compared,
  onToggleCompare,
  onOpenDetail,
}) {
  return (
    <div
      className="rounded-xl border p-4"
      style={{
        background: "var(--surface-1)",
        borderColor: compared ? "var(--series-1)" : "var(--hairline)",
      }}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p
            className="flex items-center gap-1.5 text-xs"
            style={{ color: "var(--text-muted)" }}
          >
            #{rank}
            <RankDelta delta={rankDelta} />
          </p>
          <h3 className="text-base font-semibold">
            <button
              onClick={onOpenDetail}
              className="text-left hover:underline"
              title="View player details"
            >
              {player.name}
            </button>
          </h3>
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

      {player.reasons?.length > 0 && (
        <ul className="mt-3 flex flex-wrap gap-1.5">
          {player.reasons.map((reason) => (
            <li
              key={reason}
              className="rounded-full border px-2 py-0.5 text-[11px]"
              style={{
                borderColor: "var(--hairline)",
                color: "var(--text-secondary)",
              }}
            >
              {reason}
            </li>
          ))}
        </ul>
      )}

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
        className="mt-3 flex items-center justify-between border-t pt-2 text-[11px]"
        style={{ borderColor: "var(--hairline)", color: "var(--text-muted)" }}
      >
        <span className="flex gap-4">
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
        </span>
        <span className="flex items-center gap-3">
          <button
            onClick={onOpenDetail}
            className="font-medium hover:underline"
            style={{ color: "var(--series-1)" }}
          >
            Details
          </button>
          <label className="flex cursor-pointer items-center gap-1.5">
            <input type="checkbox" checked={compared} onChange={onToggleCompare} />
            Compare
          </label>
        </span>
      </div>
    </div>
  );
}
