import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";
import { Button } from "./ui/button";

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
}

export class ErrorBoundary extends Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  state: ErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("SmartQueue frontend rendering error", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <main className="flex min-h-screen items-center justify-center bg-background px-5 text-foreground">
          <section className="surface-card w-full max-w-md rounded-2xl p-8 text-center">
            <span className="mx-auto flex size-12 items-center justify-center rounded-full bg-amber-500/10 text-amber-600">
              <AlertTriangle aria-hidden="true" size={22} />
            </span>
            <h1 className="mt-5 text-xl font-semibold">Something went wrong</h1>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              SmartQueue could not display this page. Try reloading to continue.
            </p>
            <Button className="mt-6" onClick={() => window.location.reload()}>
              <RotateCcw aria-hidden="true" size={16} />
              Reload page
            </Button>
          </section>
        </main>
      );
    }
    return this.props.children;
  }
}
