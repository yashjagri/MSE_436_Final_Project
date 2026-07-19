// Mini horizontal bar pair comparing the player's value to the ideal
// vector's value for one feature, labelled with both numbers.
export default function FeatureBar({ label, playerValue, idealValue }) {
  const max = Math.max(playerValue, idealValue, 0.0001);
  const width = (value) => `${Math.max((value / max) * 100, 0)}%`;

  return (
    <div>
      <div className="flex justify-between text-[11px]">
        <span style={{ color: "var(--text-secondary)" }}>{label}</span>
        <span style={{ color: "var(--text-muted)" }}>
          {playerValue} vs ideal {idealValue}
        </span>
      </div>
      <div className="mt-1 space-y-0.5">
        <div
          className="h-2 rounded-r"
          style={{ width: width(playerValue), background: "var(--series-1)" }}
          aria-label={`Player: ${playerValue}`}
        />
        <div
          className="h-2 rounded-r"
          style={{ width: width(idealValue), background: "var(--benchmark)" }}
          aria-label={`Ideal: ${idealValue}`}
        />
      </div>
    </div>
  );
}
