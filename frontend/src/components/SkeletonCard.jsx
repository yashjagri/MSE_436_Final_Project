// Placeholder card shown while the shortlist is being scored, so the first
// load reads as "working" rather than an empty page. Mirrors PlayerCard's
// layout (identity line, reasons chips, feature bars) at low contrast.
function Block({ className }) {
  return (
    <div
      className={`animate-pulse rounded ${className}`}
      style={{ background: "var(--hairline)" }}
    />
  );
}

export default function SkeletonCard() {
  return (
    <div
      className="rounded-xl border p-4"
      style={{ background: "var(--surface-1)", borderColor: "var(--hairline)" }}
      aria-hidden="true"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-2">
          <Block className="h-2.5 w-6" />
          <Block className="h-4 w-32" />
          <Block className="h-2.5 w-44" />
        </div>
        <Block className="h-6 w-9 rounded-full" />
      </div>

      <div className="mt-3 flex gap-1.5">
        <Block className="h-4 w-20 rounded-full" />
        <Block className="h-4 w-24 rounded-full" />
      </div>

      <div className="mt-4 space-y-3">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="space-y-1">
            <Block className="h-2.5 w-28" />
            <Block className="h-2 w-full" />
          </div>
        ))}
      </div>
    </div>
  );
}
