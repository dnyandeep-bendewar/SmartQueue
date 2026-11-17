import {
  ArrowRight,
  Check,
  CheckCircle2,
  Clipboard,
  Clock3,
  FileBadge,
  GraduationCap,
  HelpCircle,
  LoaderCircle,
  RotateCw,
  Ticket,
  WalletCards,
  XCircle,
} from "lucide-react";
import axios from "axios";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { PageHeader } from "../components/PageHeader";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card, CardContent } from "../components/ui/card";
import { LoadingState } from "../components/LoadingState";
import {
  fetchCounters,
  fetchServices,
  issueVisitorToken,
  trackVisitorToken,
  type PublicCounter,
  type ServiceType,
  type TrackedToken,
  type TokenIssue,
} from "../services/visitor";

const serviceDetails: Record<
  string,
  { description: string; icon: typeof FileBadge }
> = {
  Certificate: {
    description: "Certificates and official documents",
    icon: FileBadge,
  },
  "Fee Payment": {
    description: "Tuition, fees and payment support",
    icon: WalletCards,
  },
  "General Enquiry": {
    description: "Questions and campus information",
    icon: HelpCircle,
  },
  Admission: {
    description: "Admissions and enrollment assistance",
    icon: GraduationCap,
  },
};

interface PendingIssue {
  key: string;
  body: { counter_id: number; visitor_name?: string };
}

function getErrorMessage(error: unknown, fallback: string): string {
  if (!axios.isAxiosError(error)) return fallback;
  if (!error.response) {
    return "We could not reach SmartQueue. Check your connection and retry.";
  }
  if (error.response.status === 404) {
    return fallback;
  }
  if (error.response.status === 409) {
    return "The request could not be completed because the queue changed. Please refresh and try again.";
  }
  if (error.response.status >= 500) {
    return "SmartQueue is temporarily unavailable. Please try again shortly.";
  }
  return fallback;
}

function newIdempotencyKey(): string {
  if (typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  const bytes = crypto.getRandomValues(new Uint8Array(24));
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export function VisitorPage() {
  const [services, setServices] = useState<ServiceType[]>([]);
  const [servicesLoading, setServicesLoading] = useState(true);
  const [servicesError, setServicesError] = useState("");
  const [selectedService, setSelectedService] = useState<ServiceType | null>(null);

  const [counters, setCounters] = useState<PublicCounter[]>([]);
  const [recommendedCounterId, setRecommendedCounterId] = useState<number | null>(
    null,
  );
  const [countersLoading, setCountersLoading] = useState(false);
  const [countersError, setCountersError] = useState("");
  const [selectedCounterId, setSelectedCounterId] = useState<number | null>(null);
  const [counterRefresh, setCounterRefresh] = useState(0);

  const [visitorName, setVisitorName] = useState("");
  const [issueLoading, setIssueLoading] = useState(false);
  const [issueError, setIssueError] = useState("");
  const [pendingIssue, setPendingIssue] = useState<PendingIssue | null>(null);
  const [issuedToken, setIssuedToken] = useState<TokenIssue | null>(null);
  const [copiedReference, setCopiedReference] = useState(false);

  const [trackingReferenceInput, setTrackingReferenceInput] = useState("");
  const [trackingLoading, setTrackingLoading] = useState(false);
  const [trackingError, setTrackingError] = useState("");
  const [trackedToken, setTrackedToken] = useState<TrackedToken | null>(null);

  useEffect(() => {
    let active = true;
    setServicesLoading(true);
    fetchServices()
      .then((items) => {
        if (active) {
          setServices(items);
          setServicesError("");
        }
      })
      .catch((error: unknown) => {
        if (active) {
          setServicesError(
            getErrorMessage(error, "Services could not be loaded. Please retry."),
          );
        }
      })
      .finally(() => {
        if (active) setServicesLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!selectedService) {
      setCounters([]);
      setSelectedCounterId(null);
      return;
    }

    let active = true;
    setCountersLoading(true);
    setCountersError("");
    setCounters([]);
    setRecommendedCounterId(null);
    setSelectedCounterId(null);
    fetchCounters(selectedService)
      .then((result) => {
        if (active) {
          setCounters(result.counters);
          setRecommendedCounterId(result.recommended_counter_id);
          setCountersError("");
        }
      })
      .catch((error: unknown) => {
        if (active) {
          setCountersError(
            getErrorMessage(error, "Counters could not be loaded. Please retry."),
          );
        }
      })
      .finally(() => {
        if (active) setCountersLoading(false);
      });
    return () => {
      active = false;
    };
  }, [selectedService, counterRefresh]);

  const selectedCounter = useMemo(
    () => counters.find((counter) => counter.counter_id === selectedCounterId),
    [counters, selectedCounterId],
  );

  const submitIssue = useCallback(
    async (attempt: PendingIssue) => {
      setIssueLoading(true);
      setIssueError("");
      setCopiedReference(false);
      try {
        const result = await issueVisitorToken(attempt.body, attempt.key);
        setIssuedToken(result);
        setPendingIssue(null);
        setTrackedToken(null);
      } catch (error) {
        setIssueError(
          getErrorMessage(error, "Your token could not be issued. Please try again."),
        );
        if (axios.isAxiosError(error) && error.response && error.response.status < 500) {
          setPendingIssue(null);
        }
      } finally {
        setIssueLoading(false);
      }
    },
    [],
  );

  const handleIssue = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (pendingIssue) {
      void submitIssue(pendingIssue);
      return;
    }
    if (!selectedCounter) return;
    const trimmedName = visitorName.trim();
    const body = {
      counter_id: selectedCounter.counter_id,
      ...(trimmedName ? { visitor_name: trimmedName } : {}),
    };
    const attempt = { key: newIdempotencyKey(), body };
    setPendingIssue(attempt);
    setIssueError("");
    setIssuedToken(null);
    void submitIssue(attempt);
  };

  const refreshTracking = async (reference: string) => {
    setTrackingError("");
    setTrackedToken(null);
    setTrackingLoading(true);
    try {
      setTrackedToken(await trackVisitorToken(reference));
    } catch (error) {
      setTrackingError(
        getErrorMessage(
          error,
          "No token was found with that tracking reference. Check it and try again.",
        ),
      );
    } finally {
      setTrackingLoading(false);
    }
  };

  const handleTrack = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void refreshTracking(trackingReferenceInput.trim());
  };

  const copyReference = async () => {
    if (!issuedToken) return;
    try {
      await navigator.clipboard.writeText(issuedToken.tracking_reference);
      setCopiedReference(true);
    } catch {
      setCopiedReference(false);
      setIssueError(
        "Clipboard access is unavailable. Select and copy the tracking reference directly.",
      );
    }
  };

  const trackingStatus =
    trackedToken?.status === "Waiting"
      ? "Waiting"
      : trackedToken?.status === "Serving"
        ? "Now being served"
        : "Service complete";

  return (
    <div className="space-y-10 sm:space-y-12">
      <PageHeader
        eyebrow="VISITOR EXPERIENCE"
        title="Visitor Portal"
        description="Choose a service, compare current counter estimates, and keep track of your visit."
      />

      <section aria-labelledby="services-heading">
        <div className="mb-5">
          <h2 className="text-xl font-semibold text-foreground" id="services-heading">
            1. Choose a service
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Select the service you need to see its active counters.
          </p>
        </div>
        {servicesLoading ? (
          <LoadingState label="Loading available services" />
        ) : servicesError ? (
          <ErrorState
            message={servicesError}
            onRetry={() => {
              setServicesLoading(true);
              setServicesError("");
              fetchServices()
                .then(setServices)
                .catch((error: unknown) =>
                  setServicesError(
                    getErrorMessage(error, "Services could not be loaded. Please retry."),
                  ),
                )
                .finally(() => setServicesLoading(false));
            }}
          />
        ) : services.length === 0 ? (
          <EmptyState message="No services are available right now." />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {services.map((service) => {
              const details = serviceDetails[service];
              const Icon = details?.icon ?? HelpCircle;
              const selected = selectedService === service;
              return (
                <button
                  aria-pressed={selected}
                  className={`surface-card rounded-2xl p-4 text-left transition hover:border-accent/50 sm:p-5 ${selected ? "border-accent ring-2 ring-accent/20" : ""}`}
                  key={service}
                  onClick={() => {
                    setSelectedService(service);
                    setIssuedToken(null);
                    setPendingIssue(null);
                    setIssueError("");
                  }}
                  type="button"
                >
                  <span
                    className={`flex size-10 items-center justify-center rounded-xl ${selected ? "bg-accent text-slate-950" : "bg-soft-accent text-accent"}`}
                  >
                    <Icon aria-hidden="true" size={19} />
                  </span>
                  <span className="mt-4 block font-semibold text-foreground">
                    {service}
                  </span>
                  <span className="mt-1 block text-xs leading-5 text-muted-foreground">
                    {details?.description ?? "College service"}
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </section>

      {selectedService && (
        <section aria-labelledby="counters-heading">
          <div className="mb-5">
            <p className="text-xs font-bold tracking-[0.14em] text-accent uppercase">
              {selectedService}
            </p>
            <h2 className="mt-1 text-xl font-semibold text-foreground" id="counters-heading">
              2. Compare counters
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Estimates are provided by the queue prediction service when available.
            </p>
          </div>
          {countersLoading ? (
            <LoadingState label="Checking active counters and estimates" />
          ) : countersError ? (
            <ErrorState
              message={countersError}
              onRetry={() => setCounterRefresh((value) => value + 1)}
            />
          ) : counters.length === 0 ? (
            <EmptyState message="There are no active counters for this service right now. Please check again later." />
          ) : (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {counters.map((counter) => {
                const recommended =
                  counter.counter_id === recommendedCounterId;
                const selected = counter.counter_id === selectedCounterId;
                const prediction = counter.prediction;
                return (
                  <button
                    aria-pressed={selected}
                    className={`surface-card rounded-2xl p-5 text-left transition hover:border-accent/50 ${recommended ? "border-accent/50" : ""} ${selected ? "ring-2 ring-accent/30" : ""}`}
                    key={counter.counter_id}
                    onClick={() => {
                      setSelectedCounterId(counter.counter_id);
                      setPendingIssue(null);
                      setIssuedToken(null);
                      setIssueError("");
                    }}
                    type="button"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-xs text-muted-foreground">
                          Service counter
                        </p>
                        <h3 className="mt-1 truncate text-base font-semibold text-foreground">
                          {counter.counter_name}
                        </h3>
                      </div>
                      {recommended && <Badge>Recommended</Badge>}
                    </div>
                    <div className="mt-5 grid grid-cols-2 gap-3">
                      <div className="rounded-xl bg-background p-3">
                        <p className="text-xs text-muted-foreground">
                          People waiting
                        </p>
                        <p className="mt-1 text-lg font-semibold text-foreground">
                          {counter.people_waiting}
                        </p>
                      </div>
                      <div className="rounded-xl bg-background p-3">
                        <p className="text-xs text-muted-foreground">
                          Predicted wait
                        </p>
                        {prediction.available &&
                        prediction.predicted_wait_minutes !== null ? (
                          <p className="mt-1 flex items-center gap-1.5 text-lg font-semibold text-foreground">
                            <Clock3 aria-hidden="true" className="text-accent" size={15} />
                            {prediction.predicted_wait_minutes} min
                          </p>
                        ) : (
                          <p className="mt-1 text-sm font-medium text-muted-foreground">
                            Estimate unavailable
                          </p>
                        )}
                      </div>
                    </div>
                    {selected && (
                      <span className="mt-4 flex items-center gap-1.5 text-xs font-semibold text-accent">
                        <Check aria-hidden="true" size={14} />
                        Selected for token
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          )}
        </section>
      )}

      {selectedCounter && (
        <section aria-labelledby="issue-heading">
          <div className="mb-5">
            <h2 className="text-xl font-semibold text-foreground" id="issue-heading">
              3. Get your digital token
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Your token is assigned to {selectedCounter.counter_name}.
            </p>
          </div>
          <Card>
            <CardContent className="grid gap-7 lg:grid-cols-[1fr_0.85fr]">
              <form className="space-y-4" onSubmit={handleIssue}>
                <label className="block text-sm font-medium text-foreground" htmlFor="visitor-name">
                  Name <span className="font-normal text-muted-foreground">(optional)</span>
                </label>
                <input
                  autoComplete="name"
                  className="min-h-11 w-full rounded-xl border border-border bg-background px-3.5 text-sm text-foreground placeholder:text-muted-foreground focus:border-accent focus:outline-none"
                  id="visitor-name"
                  maxLength={100}
                  onChange={(event) => setVisitorName(event.target.value)}
                  placeholder="Enter your name"
                  value={visitorName}
                />
                <Button
                  className="w-full sm:w-auto"
                  disabled={issueLoading}
                  type="submit"
                >
                  {issueLoading ? (
                    <LoaderCircle aria-hidden="true" className="animate-spin" size={17} />
                  ) : pendingIssue ? (
                    <RotateCw aria-hidden="true" size={17} />
                  ) : (
                    <Ticket aria-hidden="true" size={17} />
                  )}
                  {issueLoading
                    ? "Issuing token..."
                    : pendingIssue
                      ? "Retry token request"
                      : "Generate my token"}
                </Button>
                {pendingIssue && !issueLoading && (
                  <p className="text-xs leading-5 text-muted-foreground">
                    Retrying with the same request reference prevents duplicate tokens.
                  </p>
                )}
                {issueError && (
                  <p className="text-sm text-red-600 dark:text-red-300" role="alert">
                    {issueError}
                  </p>
                )}
              </form>

              {issuedToken ? (
                <div className="rounded-2xl border border-[var(--soft-accent-border)] bg-[var(--soft-accent)] p-5 sm:p-6">
                  <div className="flex items-center gap-2 text-sm font-semibold text-accent">
                    <CheckCircle2 aria-hidden="true" size={18} />
                    Token issued
                  </div>
                  <p className="mt-4 text-xs text-muted-foreground">Your token number</p>
                  <p className="mt-1 break-all text-3xl font-bold tracking-tight text-foreground">
                    {issuedToken.token_number}
                  </p>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <Badge>{selectedService}</Badge>
                    <Badge>{selectedCounter.counter_name}</Badge>
                    <Badge>{issuedToken.status}</Badge>
                  </div>
                  {selectedCounter.prediction.available &&
                    selectedCounter.prediction.predicted_wait_minutes !== null && (
                      <p className="mt-4 flex items-center gap-2 text-sm text-foreground">
                        <Clock3 aria-hidden="true" className="text-accent" size={16} />
                        Current estimate:{" "}
                        <strong>
                          {selectedCounter.prediction.predicted_wait_minutes} min
                        </strong>
                      </p>
                    )}
                  {!selectedCounter.prediction.available && (
                    <p className="mt-4 text-sm text-muted-foreground">
                      A waiting-time estimate is currently unavailable.
                    </p>
                  )}
                  {issuedToken.queue_position !== null && (
                    <p className="mt-2 text-sm text-muted-foreground">
                      {issuedToken.queue_position === 0
                        ? "You are next in line."
                        : `${issuedToken.queue_position} people ahead of you.`}
                    </p>
                  )}
                  <div className="mt-5 border-t border-[var(--soft-accent-border)] pt-4">
                    <p className="text-xs font-semibold text-foreground">
                      Save your secure tracking reference
                    </p>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">
                      This reference is shown only now. Keep it private; anyone with it can view this token.
                    </p>
                    <div className="mt-3 flex flex-col gap-2 sm:flex-row">
                      <code className="min-w-0 flex-1 overflow-hidden rounded-lg border border-border bg-surface px-3 py-2.5 text-xs break-all text-foreground">
                        {issuedToken.tracking_reference}
                      </code>
                      <Button
                        aria-label="Copy secure tracking reference"
                        className="shrink-0"
                        onClick={() => void copyReference()}
                        variant="secondary"
                      >
                        {copiedReference ? (
                          <Check aria-hidden="true" size={16} />
                        ) : (
                          <Clipboard aria-hidden="true" size={16} />
                        )}
                        {copiedReference ? "Copied" : "Copy"}
                      </Button>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="flex flex-col justify-center rounded-2xl border border-dashed border-border bg-background/70 p-5 sm:p-6">
                  <span className="flex size-10 items-center justify-center rounded-xl bg-soft-accent text-accent">
                    <Ticket aria-hidden="true" size={19} />
                  </span>
                  <p className="mt-4 text-sm font-semibold text-foreground">
                    Your token details will appear here
                  </p>
                  <p className="mt-1 text-sm leading-6 text-muted-foreground">
                    Select a counter and request a token to receive a secure tracking reference.
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        </section>
      )}

      <section aria-labelledby="tracking-heading">
        <div className="mb-5">
          <h2 className="text-xl font-semibold text-foreground" id="tracking-heading">
            Check an existing token
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Enter the secure tracking reference you saved when your token was issued.
          </p>
        </div>
        <Card>
          <CardContent>
            <form className="flex flex-col gap-3 sm:flex-row" onSubmit={handleTrack}>
              <label className="sr-only" htmlFor="tracking-reference">
                Secure tracking reference
              </label>
              <input
                autoComplete="off"
                className="min-h-11 min-w-0 flex-1 rounded-xl border border-border bg-background px-3.5 text-sm text-foreground placeholder:text-muted-foreground focus:border-accent focus:outline-none"
                id="tracking-reference"
                onChange={(event) => setTrackingReferenceInput(event.target.value)}
                placeholder="Paste your tracking reference"
                spellCheck={false}
                value={trackingReferenceInput}
              />
              <Button disabled={trackingLoading || !trackingReferenceInput.trim()} type="submit">
                {trackingLoading ? (
                  <LoaderCircle aria-hidden="true" className="animate-spin" size={17} />
                ) : (
                  <ArrowRight aria-hidden="true" size={17} />
                )}
                {trackingLoading ? "Checking..." : "Track token"}
              </Button>
            </form>
            {trackingError && (
              <p className="mt-4 text-sm text-red-600 dark:text-red-300" role="alert">
                {trackingError}
              </p>
            )}
            {trackedToken && (
              <div className="mt-5 rounded-2xl border border-border bg-background p-4 sm:p-5">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <p className="text-xs text-muted-foreground">Token</p>
                    <p className="mt-1 text-xl font-bold text-foreground">
                      {trackedToken.token_number}
                    </p>
                  </div>
                  <Badge>
                    <span className="size-1.5 rounded-full bg-accent" />
                    {trackingStatus}
                  </Badge>
                </div>
                <div className="mt-4 grid gap-3 text-sm sm:grid-cols-3">
                  <TokenDetail label="Service" value={trackedToken.service_type} />
                  <TokenDetail label="Counter" value={trackedToken.counter_name} />
                  <TokenDetail
                    label="Created"
                    value={new Date(trackedToken.created_at).toLocaleString()}
                  />
                </div>
                {trackedToken.status === "Waiting" &&
                  trackedToken.queue_position !== null && (
                    <p className="mt-4 text-sm font-medium text-foreground">
                      {trackedToken.queue_position === 0
                        ? "You are next in line."
                        : `${trackedToken.queue_position} people ahead of you.`}
                    </p>
                  )}
                {trackedToken.status === "Serving" && (
                  <p className="mt-4 flex items-center gap-2 text-sm font-semibold text-accent">
                    <Clock3 aria-hidden="true" size={16} />
                    Now being served
                  </p>
                )}
                {trackedToken.status === "Served" && (
                  <p className="mt-4 flex items-center gap-2 text-sm font-semibold text-accent">
                    <CheckCircle2 aria-hidden="true" size={16} />
                    Your service is complete.
                  </p>
                )}
                <Button
                  className="mt-5"
                  disabled={trackingLoading}
                  onClick={() =>
                    void refreshTracking(trackingReferenceInput.trim())
                  }
                  variant="secondary"
                >
                  <RotateCw aria-hidden="true" size={15} />
                  Refresh status
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}

function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <Card>
      <CardContent className="flex flex-col items-start gap-4 sm:flex-row sm:items-center">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-red-500/10 text-red-600 dark:text-red-300">
          <XCircle aria-hidden="true" size={19} />
        </span>
        <p className="flex-1 text-sm text-foreground" role="alert">
          {message}
        </p>
        <Button onClick={onRetry} variant="secondary">
          <RotateCw aria-hidden="true" size={15} />
          Retry
        </Button>
      </CardContent>
    </Card>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 text-sm text-muted-foreground">
        <HelpCircle aria-hidden="true" className="shrink-0 text-accent" size={18} />
        {message}
      </CardContent>
    </Card>
  );
}

function TokenDetail({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 truncate font-medium text-foreground">{value}</p>
    </div>
  );
}
