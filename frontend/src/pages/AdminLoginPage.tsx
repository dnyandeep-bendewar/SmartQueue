import axios from "axios";
import {
  Activity,
  ArrowRight,
  Eye,
  EyeOff,
  LoaderCircle,
  LockKeyhole,
  ShieldCheck,
} from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../components/auth/AuthProvider";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card, CardContent } from "../components/ui/card";
import { LoadingState } from "../components/LoadingState";

interface LoginLocationState {
  from?: string;
}

function loginErrorMessage(error: unknown): string {
  if (!axios.isAxiosError(error)) {
    return "Sign in could not be completed. Please try again.";
  }
  if (!error.response) {
    return "SmartQueue could not be reached. Check your connection and try again.";
  }
  if (error.response.status === 401) {
    return "The username or password is incorrect. Please try again.";
  }
  if (error.response.status === 429) {
    return "There have been too many attempts. Please wait a while before trying again.";
  }
  if (error.response.status === 403) {
    return "This request could not be verified. Reload the page and try again.";
  }
  if (error.response.status >= 500) {
    return "The sign-in service is temporarily unavailable. Please try again shortly.";
  }
  return "Sign in could not be completed. Check your details and try again.";
}

function safeReturnPath(value: string | undefined): string {
  return value === "/analytics" ? value : "/admin";
}

export function AdminLoginPage() {
  const { state, login, checkSession } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const locationState = location.state as LoginLocationState | null;
  const returnPath = safeReturnPath(locationState?.from);

  if (state.status === "checking") {
    return <LoadingState label="Checking administrator session" />;
  }

  if (state.status === "authenticated") {
    return <Navigate replace to={returnPath} />;
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const normalizedUsername = username.trim();
    if (!normalizedUsername || !password) {
      setErrorMessage("Enter both your username and password.");
      return;
    }

    setSubmitting(true);
    setErrorMessage("");
    try {
      await login(normalizedUsername, password);
      setPassword("");
      navigate(returnPath, { replace: true });
    } catch (error) {
      setErrorMessage(loginErrorMessage(error));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto grid min-h-[calc(100vh-160px)] w-full max-w-5xl items-center gap-8 lg:grid-cols-[1fr_0.9fr] lg:gap-14">
      <section className="hidden lg:block">
        <Badge>
          <ShieldCheck aria-hidden="true" size={14} />
          Secure operations workspace
        </Badge>
        <h1 className="mt-6 max-w-lg text-4xl leading-tight font-semibold tracking-tight text-foreground xl:text-5xl">
          Keep every queue moving with confidence.
        </h1>
        <p className="mt-5 max-w-lg text-base leading-7 text-muted-foreground">
          Sign in to manage service counters and support a smoother visitor
          experience.
        </p>
        <div className="mt-8 flex items-center gap-3 text-sm text-muted-foreground">
          <span className="flex size-10 items-center justify-center rounded-xl bg-soft-accent text-accent">
            <Activity aria-hidden="true" size={19} />
          </span>
          Less waiting. Better experiences.
        </div>
      </section>

      <Card className="w-full max-w-lg justify-self-center">
        <CardContent className="p-6 sm:p-8">
          <div className="flex size-11 items-center justify-center rounded-xl bg-accent text-slate-950">
            <LockKeyhole aria-hidden="true" size={20} />
          </div>
          <p className="mt-6 text-xs font-bold tracking-[0.15em] text-accent uppercase">
            ADMINISTRATOR ACCESS
          </p>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight text-foreground">
            Welcome back
          </h2>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            Sign in to continue to the SmartQueue operations workspace.
          </p>

          {state.status === "error" && (
            <div className="mt-5 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3.5">
              <p className="text-sm text-foreground">{state.message}</p>
              <Button
                className="mt-3"
                onClick={() => void checkSession()}
                size="default"
                variant="secondary"
              >
                Retry session check
              </Button>
            </div>
          )}

          {errorMessage && (
            <p
              aria-live="polite"
              className="mt-5 rounded-xl border border-red-500/30 bg-red-500/10 p-3.5 text-sm text-red-700 dark:text-red-200"
              role="alert"
            >
              {errorMessage}
            </p>
          )}

          <form className="mt-6 space-y-4" onSubmit={handleSubmit}>
            <div>
              <label
                className="mb-1.5 block text-sm font-medium text-foreground"
                htmlFor="admin-username"
              >
                Username
              </label>
              <input
                autoComplete="username"
                className="min-h-11 w-full rounded-xl border border-border bg-background px-3.5 text-sm text-foreground placeholder:text-muted-foreground focus:border-accent focus:outline-none"
                id="admin-username"
                maxLength={150}
                onChange={(event) => setUsername(event.target.value)}
                required
                value={username}
              />
            </div>
            <div>
              <label
                className="mb-1.5 block text-sm font-medium text-foreground"
                htmlFor="admin-password"
              >
                Password
              </label>
              <div className="relative">
                <input
                  autoComplete="current-password"
                  className="min-h-11 w-full rounded-xl border border-border bg-background px-3.5 pr-12 text-sm text-foreground placeholder:text-muted-foreground focus:border-accent focus:outline-none"
                  id="admin-password"
                  maxLength={1024}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                  type={showPassword ? "text" : "password"}
                  value={password}
                />
                <button
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  className="absolute inset-y-0 right-0 flex w-11 items-center justify-center text-muted-foreground hover:text-foreground"
                  onClick={() => setShowPassword((value) => !value)}
                  type="button"
                >
                  {showPassword ? (
                    <EyeOff aria-hidden="true" size={17} />
                  ) : (
                    <Eye aria-hidden="true" size={17} />
                  )}
                </button>
              </div>
            </div>
            <Button className="mt-2 w-full" disabled={submitting} type="submit">
              {submitting ? (
                <LoaderCircle
                  aria-hidden="true"
                  className="animate-spin"
                  size={17}
                />
              ) : (
                <ArrowRight aria-hidden="true" size={17} />
              )}
              {submitting ? "Signing in..." : "Sign in securely"}
            </Button>
          </form>

          <p className="mt-5 text-center text-xs leading-5 text-muted-foreground">
            Your session is protected by a secure, HttpOnly cookie. Credentials
            are never saved in this browser.
          </p>
          <Link
            className="mt-6 block text-center text-sm font-medium text-accent hover:underline"
            to="/visitor"
          >
            Continue to Visitor Portal
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}
