import type { HTMLAttributes } from "react";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  interactive?: boolean;
}

export function Card({
  className = "",
  interactive = false,
  ...props
}: CardProps) {
  return (
    <div
      className={`surface-card rounded-2xl ${interactive ? "transition duration-200 hover:-translate-y-0.5 hover:border-accent/40 hover:shadow-lg" : ""} ${className}`}
      {...props}
    />
  );
}

export function CardContent({
  className = "",
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return <div className={`p-5 sm:p-6 ${className}`} {...props} />;
}
