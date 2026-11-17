import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "./AuthProvider";
import { LoadingState } from "../LoadingState";
import { Button } from "../ui/button";

export function ProtectedRoute() {
  const { state, checkSession } = useAuth();
  const location = useLocation();

  if (state.status === "checking") {
    return <LoadingState label="Verifying administrator session" />;
  }

  if (state.status === "error") {
    return (
      <section
        aria-live="polite"
        className="surface-card mx-auto max-w-xl rounded-2xl p-6 sm:p-8"
      >
        <h1 className="text-xl font-semibold text-foreground">
          Could not verify your session
        </h1>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          {state.message}
        </p>
        <Button className="mt-5" onClick={() => void checkSession()}>
          Retry session check
        </Button>
      </section>
    );
  }

  if (state.status !== "authenticated") {
    return (
      <Navigate
        replace
        state={{ from: location.pathname }}
        to="/admin/login"
      />
    );
  }

  return <Outlet />;
}
