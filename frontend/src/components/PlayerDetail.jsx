import { useEffect, useState } from "react";
import FeatureBar from "./FeatureBar.jsx";
import { FEATURE_LABELS } from "../App.jsx";

const formatMarketValue = (eur) =>
  eur == null ? "—" : `€${(eur / 1_000_000).toFixed(1)}m`;

const badgeStyle = (score) => {
  if (score > 80) return { background: "var(--status-good)", color: "#fff" };
  if (score >= 60) return { background: "var(--status-warning)", color: "#0b0b0b" };
  return { background: "var(--status-critical)", color: "#fff" };
};

// Player headshot with a graceful initials fallback: the API-Football CDN
// occasionally 404s, and cache-less players have no photo at all.
function Avatar({ src, name }) {
  const [failed, setFailed] = useState(false);
  const initials = name
    .split(" ")
    .map((part) => part[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();

  if (!src || failed)
    return (
      <div
        className="flex h-20 w-20 shrink-0 items-center justify-center rounded-full text-xl font-semibold"
        style={{ background: "var(--hairline)", color: "var(--text-secondary)" }}
      >
        {initials}
      </div>
    );

  return (
    <img
      src={src}
      alt={name}
      onError={() => setFailed(true)}
      className="h-20 w-20 shrink-0 rounded-full object-cover"
      style={{ background: "var(--hairline)" }}
    />
  );
}

// One "label: value" fact, rendered only when the value is present.
function Fact({ label, value }) {
  if (value == null || value === "") return null;
  return (
    <div>
      <dt className="text-[11px]" style={{ color: "var(--text-muted)" }}>
        {label}
      </dt>
      <dd className="text-sm font-medium">{value}</dd>
    </div>
  );
}

// Full-screen drill-down for a shortlisted player: photo, club, national
// team, physical profile, and the same player-vs-ideal stat breakdown the
// card shows, plus season totals from the enrichment cache.
export default function PlayerDetail({ player, onClose }) {
  // Close on Escape, and lock body scroll while the modal is open.
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [onClose]);

  const d = player.details || {};
  const height = d.height ? `${d.height} cm` : null;
  const weight = d.weight ? `${d.weight} kg` : null;
  const birthplace = [d.birth_place, d.birth_country]
    .filter(Boolean)
    .join(", ");

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto p-4 sm:p-8"
      style={{ background: "rgba(0,0,0,0.55)" }}
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={`${player.name} details`}
    >
      <div
        className="w-full max-w-2xl rounded-xl border shadow-xl"
        style={{ background: "var(--surface-1)", borderColor: "var(--hairline)" }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          className="flex items-start gap-4 border-b p-5"
          style={{ borderColor: "var(--hairline)" }}
        >
          <Avatar src={d.photo} name={player.name} />
          <div className="min-w-0 flex-1">
            <div className="flex items-start justify-between gap-2">
              <h2 className="truncate text-lg font-semibold">{player.name}</h2>
              <span
                className="shrink-0 rounded-full px-2.5 py-1 text-xs font-bold"
                style={badgeStyle(player.fit_score)}
                title="Fit score out of 100"
              >
                {player.fit_score}
              </span>
            </div>
            <p
              className="mt-0.5 flex flex-wrap items-center gap-x-2 text-sm"
              style={{ color: "var(--text-secondary)" }}
            >
              {d.club_logo && (
                <img
                  src={d.club_logo}
                  alt=""
                  className="inline-block h-4 w-4 object-contain"
                />
              )}
              <span>{d.club || player.league}</span>
              <span style={{ color: "var(--text-muted)" }}>· {player.position}</span>
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="shrink-0 rounded-md px-2 py-1 text-lg leading-none"
            style={{ color: "var(--text-muted)" }}
          >
            ×
          </button>
        </div>

        <div className="space-y-5 p-5">
          {/* Identity / physical profile */}
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3">
            <Fact label="League" value={player.league} />
            <Fact label="National team" value={d.nationality} />
            <Fact label="Age" value={`${player.age} yrs`} />
            <Fact label="Market value" value={formatMarketValue(player.market_value_eur)} />
            <Fact label="Height" value={height} />
            <Fact label="Weight" value={weight} />
            <Fact label="Born" value={birthplace || null} />
          </dl>

          {/* Season totals from the enrichment cache */}
          {(d.appearances || d.minutes || d.rating) && (
            <div>
              <h3 className="mb-2 text-sm font-semibold">2024/25 season</h3>
              <dl className="grid grid-cols-3 gap-4">
                <Fact label="Appearances" value={d.appearances} />
                <Fact label="Minutes" value={d.minutes} />
                <Fact label="Avg rating" value={d.rating} />
              </dl>
            </div>
          )}

          {/* Plain-language reasons */}
          {player.reasons?.length > 0 && (
            <ul className="flex flex-wrap gap-1.5">
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

          {/* Key stats vs the ideal profile */}
          <div>
            <h3 className="mb-3 text-sm font-semibold">
              Key stats <span style={{ color: "var(--text-muted)" }}>vs ideal</span>
            </h3>
            <div className="space-y-3">
              {player.breakdown.map((item) => (
                <FeatureBar
                  key={item.feature}
                  label={FEATURE_LABELS[item.feature] ?? item.feature}
                  playerValue={item.player_value}
                  idealValue={item.ideal_value}
                />
              ))}
            </div>
          </div>

          {!player.details && (
            <p className="text-xs" style={{ color: "var(--text-muted)" }}>
              Extended profile (photo, club, national team) unavailable for this
              player — not found in the API-Football cache.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
