import { LoaderCircle } from "lucide-react";

export function LoadingState({ label = "Loading SmartQueue" }: { label?: string }) {
  return (
    <div
      aria-live="polite"
      className="flex min-h-48 items-center justify-center gap-3 text-sm text-muted-foreground"
    >
      <LoaderCircle aria-hidden="true" className="animate-spin text-accent" size={18} />
      <span>{label}</span>
    </div>
  );
}
