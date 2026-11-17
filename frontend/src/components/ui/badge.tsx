import type { HTMLAttributes } from "react";

export function Badge({
  className = "",
  ...props
}: HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border border-[var(--soft-accent-border)] bg-[var(--soft-accent)] px-3 py-1 text-xs font-semibold text-accent ${className}`}
      {...props}
    />
  );
}
