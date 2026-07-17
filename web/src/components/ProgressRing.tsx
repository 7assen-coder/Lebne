"use client";

export function ProgressRing({
  done,
  total,
  percent,
  size = "md",
}: {
  done: number;
  total: number;
  percent: number;
  size?: "md" | "lg";
}) {
  const large = size === "lg";
  const box = large ? 96 : 44;
  const r = large ? 36 : 18;
  const stroke = large ? 7 : 4;
  const c = 2 * Math.PI * r;
  const offset = c - (Math.min(percent, 100) / 100) * c;
  const mid = box / 2;

  return (
    <div
      className="flex min-w-0 items-center"
      style={{ gap: large ? "clamp(0.6rem, 0.4rem + 1vw, 1.25rem)" : "0.6rem" }}
      title={`${done} / ${total}`}
    >
      <div
        className="relative shrink-0"
        style={
          large
            ? {
                width: "clamp(3.5rem, 2.4rem + 4vw, 6rem)",
                height: "clamp(3.5rem, 2.4rem + 4vw, 6rem)",
              }
            : { width: box, height: box }
        }
      >
        <svg
          viewBox={`0 0 ${box} ${box}`}
          className={`-rotate-90 ${large ? "h-full w-full" : ""}`}
          width={large ? undefined : box}
          height={large ? undefined : box}
          aria-hidden
        >
          <circle
            cx={mid}
            cy={mid}
            r={r}
            fill="none"
            stroke="rgba(242,245,247,0.1)"
            strokeWidth={stroke}
          />
          <circle
            cx={mid}
            cy={mid}
            r={r}
            fill="none"
            stroke="var(--accent)"
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={c}
            strokeDashoffset={offset}
            className="transition-all duration-500"
          />
        </svg>
        {large && (
          <div className="absolute inset-0 flex items-center justify-center">
            <span
              className="font-display tabular-nums text-[var(--accent)]"
              style={{ fontSize: "clamp(0.95rem, 0.7rem + 1.2vw, 1.75rem)" }}
            >
              {percent}%
            </span>
          </div>
        )}
      </div>
      <div className="min-w-0">
        {!large && (
          <p className="font-display text-2xl leading-none tabular-nums">{percent}%</p>
        )}
        <p
          className="truncate tabular-nums text-[var(--muted)]"
          style={{ fontSize: large ? "var(--ui-text)" : "0.875rem" }}
        >
          <span className="font-semibold text-[var(--ink)]">{done.toLocaleString()}</span>
          <span className="mx-1.5 opacity-40">/</span>
          {total.toLocaleString()}
        </p>
      </div>
    </div>
  );
}
