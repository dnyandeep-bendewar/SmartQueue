import axios from "axios";
import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  Check,
  Clock3,
  LoaderCircle,
  Pencil,
  Plus,
  RefreshCw,
  Users,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthProvider";
import { LoadingState } from "../LoadingState";
import { PageHeader } from "../PageHeader";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Card, CardContent } from "../ui/card";
import {
  createAdminCounter,
  fetchAdminCounters,
  fetchAdminStatistics,
  fetchAdminTokens,
  fetchCounterEstimates,
  setAdminCounterStatus,
  setAdminTokenStatus,
  updateAdminCounter,
  type AdminCounter,
  type AdminStatistics,
  type AdminToken,
  type CounterEstimate,
  type CreateCounterRequest,
  type UpdateCounterRequest,
} from "../../services/admin";
import type { ServiceType, TokenStatus } from "../../services/visitor";

const SERVICE_TYPES: ServiceType[] = [
  "Certificate",
  "Fee Payment",
  "General Enquiry",
  "Admission",
];
const TOKEN_STATUSES: TokenStatus[] = ["Waiting", "Serving", "Served"];
const STATUS_TRANSITIONS: Record<TokenStatus, TokenStatus[]> = {
  Waiting: ["Serving", "Served"],
  Serving: ["Served"],
  Served: [],
};

interface CounterFormState {
  counter_name: string;
  service_type: ServiceType;
  people_waiting: string;
  active_counters: string;
  avg_service_time: string;
}

type CounterDialog =
  | { mode: "add" }
  | { mode: "edit"; counter: AdminCounter }
  | null;

function friendlyError(error: unknown): string {
  if (!axios.isAxiosError(error)) {
    return "Something went wrong. Please try again.";
  }
  if (!error.response) {
    return "Could not reach SmartQueue. Check the backend connection and retry.";
  }
  switch (error.response.status) {
    case 401:
      return "Your administrator session has expired. Sign in again to continue.";
    case 403:
      return "This action could not be verified. Refresh the page and try again.";
    case 404:
      return "That record could not be found. Refresh the dashboard and try again.";
    case 409:
      return "That queue status change is not allowed. Refresh the queue and try again.";
    case 422:
      return "Some details are invalid. Review the fields and try again.";
    case 429:
      return "Too many requests. Wait a moment and try again.";
    default:
      return error.response.status >= 500
        ? "The service is temporarily unavailable. Please try again shortly."
        : "The request could not be completed. Please try again.";
  }
}

function initialCounterForm(counter?: AdminCounter): CounterFormState {
  return {
    counter_name: counter?.counter_name ?? "",
    service_type: counter?.service_type ?? "Certificate",
    people_waiting: String(counter?.people_waiting ?? 0),
    active_counters: String(counter?.active_counters ?? 1),
    avg_service_time: String(counter?.avg_service_time ?? 5),
  };
}

function StatusBadge({ status }: { status: TokenStatus | "Active" | "Inactive" }) {
  const styles: Record<typeof status, string> = {
    Waiting: "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-200",
    Serving: "border-sky-500/30 bg-sky-500/10 text-sky-700 dark:text-sky-200",
    Served: "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-200",
    Active: "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-200",
    Inactive: "border-border bg-background text-muted-foreground",
  };
  return (
    <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${styles[status]}`}>
      {status}
    </span>
  );
}

function SectionTitle({
  eyebrow,
  title,
  detail,
  action,
}: {
  eyebrow: string;
  title: string;
  detail: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <p className="text-[11px] font-bold tracking-[0.15em] text-accent uppercase">{eyebrow}</p>
        <h2 className="mt-1 text-xl font-semibold text-foreground">{title}</h2>
        <p className="mt-1 text-sm leading-6 text-muted-foreground">{detail}</p>
      </div>
      {action}
    </div>
  );
}

function MetricCard({
  title,
  value,
  subtitle,
  icon: Icon,
  tone,
}: {
  title: string;
  value: string | number;
  subtitle: string;
  icon: typeof Users;
  tone: "teal" | "blue" | "violet" | "amber";
}) {
  const tones = {
    teal: "bg-soft-accent text-accent",
    blue: "bg-sky-500/10 text-sky-600 dark:text-sky-300",
    violet: "bg-violet-500/10 text-violet-600 dark:text-violet-300",
    amber: "bg-amber-500/10 text-amber-700 dark:text-amber-200",
  };
  return (
    <Card>
      <CardContent className="p-4 sm:p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-sm font-medium text-muted-foreground">{title}</p>
            <p className="mt-2 text-3xl font-semibold tracking-tight text-foreground">{value}</p>
          </div>
          <span className={`flex size-10 shrink-0 items-center justify-center rounded-xl ${tones[tone]}`}>
            <Icon aria-hidden="true" size={19} />
          </span>
        </div>
        <p className="mt-3 text-xs text-muted-foreground">{subtitle}</p>
      </CardContent>
    </Card>
  );
}

function EmptyState({ children }: { children: string }) {
  return (
    <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-muted-foreground">
      {children}
    </div>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  children,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1.5 text-xs font-medium text-muted-foreground">
      {label}
      <select
        className="min-h-10 rounded-xl border border-border bg-background px-3 text-sm text-foreground"
        onChange={(event) => onChange(event.target.value)}
        value={value}
      >
        {children}
      </select>
    </label>
  );
}

export function AdminDashboard() {
  const { state: authState } = useAuth();
  const csrfToken = authState.status === "authenticated" ? authState.csrfToken : "";
  const [counters, setCounters] = useState<AdminCounter[]>([]);
  const [tokens, setTokens] = useState<AdminToken[]>([]);
  const [statistics, setStatistics] = useState<AdminStatistics | null>(null);
  const [estimates, setEstimates] = useState<CounterEstimate[]>([]);
  const [recommendedCounterId, setRecommendedCounterId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [actionError, setActionError] = useState("");
  const [notice, setNotice] = useState("");
  const [dialog, setDialog] = useState<CounterDialog>(null);
  const [form, setForm] = useState<CounterFormState>(initialCounterForm);
  const [savingCounter, setSavingCounter] = useState(false);
  const [busyCounters, setBusyCounters] = useState<number[]>([]);
  const [busyTokens, setBusyTokens] = useState<number[]>([]);
  const [serviceFilter, setServiceFilter] = useState("All");
  const [statusFilter, setStatusFilter] = useState("All");

  const refreshDashboard = useCallback(async () => {
    setRefreshing(true);
    const [counterResult, tokenResult, statisticsResult, estimateResult] =
      await Promise.allSettled([
        fetchAdminCounters(),
        fetchAdminTokens(),
        fetchAdminStatistics(),
        fetchCounterEstimates(),
      ]);

    const nextErrors: Record<string, string> = {};
    if (counterResult.status === "fulfilled") {
      setCounters(counterResult.value);
    } else {
      nextErrors.counters = friendlyError(counterResult.reason);
    }
    if (tokenResult.status === "fulfilled") {
      setTokens(tokenResult.value);
    } else {
      nextErrors.tokens = friendlyError(tokenResult.reason);
    }
    if (statisticsResult.status === "fulfilled") {
      setStatistics(statisticsResult.value);
    } else {
      nextErrors.statistics = friendlyError(statisticsResult.reason);
    }
    if (estimateResult.status === "fulfilled") {
      setEstimates(estimateResult.value.counters);
      setRecommendedCounterId(estimateResult.value.recommended_counter_id);
    } else {
      nextErrors.estimates = friendlyError(estimateResult.reason);
    }
    setErrors(nextErrors);
    setLoading(false);
    setRefreshing(false);
  }, []);

  useEffect(() => {
    void refreshDashboard();
  }, [refreshDashboard]);

  const filteredTokens = useMemo(
    () =>
      tokens.filter(
        (token) =>
          (serviceFilter === "All" || token.service_type === serviceFilter) &&
          (statusFilter === "All" || token.status === statusFilter),
      ),
    [serviceFilter, statusFilter, tokens],
  );
  const peopleWaiting = counters
    .filter((counter) => counter.is_active)
    .reduce((total, counter) => total + counter.people_waiting, 0);

  const openAddDialog = () => {
    setForm(initialCounterForm());
    setDialog({ mode: "add" });
    setActionError("");
  };

  const openEditDialog = (counter: AdminCounter) => {
    setForm(initialCounterForm(counter));
    setDialog({ mode: "edit", counter });
    setActionError("");
  };

  const handleCounterSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!csrfToken) {
      setActionError("Your session is not ready. Refresh and try again.");
      return;
    }
    setSavingCounter(true);
    setActionError("");
    try {
      if (dialog?.mode === "add") {
        const payload: CreateCounterRequest = {
          counter_name: form.counter_name.trim(),
          service_type: form.service_type,
          active_counters: Number(form.active_counters),
          avg_service_time: Number(form.avg_service_time),
        };
        await createAdminCounter(payload, csrfToken);
        setNotice("Counter added successfully.");
      } else if (dialog?.mode === "edit") {
        const payload: UpdateCounterRequest = {
          people_waiting: Number(form.people_waiting),
          active_counters: Number(form.active_counters),
          avg_service_time: Number(form.avg_service_time),
          is_active: dialog.counter.is_active,
        };
        await updateAdminCounter(dialog.counter.counter_id, payload, csrfToken);
        setNotice("Counter settings updated.");
      }
      setDialog(null);
      await refreshDashboard();
    } catch (error) {
      setActionError(friendlyError(error));
    } finally {
      setSavingCounter(false);
    }
  };

  const handleCounterStatus = async (counter: AdminCounter) => {
    if (!csrfToken) return;
    setActionError("");
    setBusyCounters((ids) => [...ids, counter.counter_id]);
    try {
      await setAdminCounterStatus(counter.counter_id, !counter.is_active, csrfToken);
      setNotice(`Counter ${counter.is_active ? "deactivated" : "activated"}.`);
      await refreshDashboard();
    } catch (error) {
      setActionError(friendlyError(error));
    } finally {
      setBusyCounters((ids) => ids.filter((id) => id !== counter.counter_id));
    }
  };

  const handleTokenStatus = async (token: AdminToken, nextStatus: TokenStatus) => {
    if (!csrfToken) return;
    setActionError("");
    setBusyTokens((ids) => [...ids, token.token_id]);
    try {
      await setAdminTokenStatus(token.token_id, nextStatus, csrfToken);
      setNotice(`Token ${token.token_number} marked ${nextStatus.toLowerCase()}.`);
      await refreshDashboard();
    } catch (error) {
      setActionError(friendlyError(error));
      if (axios.isAxiosError(error) && error.response?.status === 409) {
        await refreshDashboard();
      }
    } finally {
      setBusyTokens((ids) => ids.filter((id) => id !== token.token_id));
    }
  };

  const clearNotice = () => setNotice("");

  return (
    <>
      <PageHeader
        action={
          <Button
            disabled={refreshing}
            onClick={() => {
              clearNotice();
              void refreshDashboard();
            }}
            variant="secondary"
          >
            {refreshing ? (
              <LoaderCircle aria-hidden="true" className="animate-spin" size={16} />
            ) : (
              <RefreshCw aria-hidden="true" size={16} />
            )}
            Refresh dashboard
          </Button>
        }
        description="Monitor the live queue, manage service counters, and keep visitor flow moving."
        eyebrow="OPERATIONS WORKSPACE"
        title="Admin Dashboard"
      />

      {actionError && (
        <div className="mb-5 flex items-start justify-between gap-3 rounded-xl border border-red-500/30 bg-red-500/10 p-3.5 text-sm text-red-700 dark:text-red-200" role="alert">
          <span>{actionError}</span>
          <button aria-label="Dismiss error" className="shrink-0" onClick={() => setActionError("")} type="button">
            <X aria-hidden="true" size={17} />
          </button>
        </div>
      )}
      {notice && (
        <div className="mb-5 flex items-center justify-between gap-3 rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-3.5 text-sm text-emerald-800 dark:text-emerald-200" role="status">
          <span className="flex items-center gap-2"><Check aria-hidden="true" size={16} />{notice}</span>
          <button aria-label="Dismiss notice" className="shrink-0" onClick={clearNotice} type="button"><X aria-hidden="true" size={17} /></button>
        </div>
      )}

      {loading ? (
        <LoadingState label="Loading live queue and counter data" />
      ) : (
        <div className="space-y-10">
          <section aria-label="Dashboard overview">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-foreground">Queue at a glance</h2>
                <p className="mt-1 text-sm text-muted-foreground">Current operational totals from SmartQueue.</p>
              </div>
              <Link className="text-sm font-semibold text-accent hover:underline" to="/analytics">View analytics</Link>
            </div>
            {errors.statistics && <ResourceError message={errors.statistics} onRetry={() => void refreshDashboard()} />}
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <MetricCard title="People waiting" value={errors.counters ? "—" : peopleWaiting} subtitle="Reported at active service counters" icon={Users} tone="teal" />
              <MetricCard title="Active counters" value={statistics?.active_counter_count ?? "—"} subtitle="Currently open for service" icon={Activity} tone="blue" />
              <MetricCard title="Total tokens" value={errors.tokens ? "—" : tokens.length} subtitle="All current and completed queue records" icon={Clock3} tone="violet" />
              <MetricCard title="Currently served" value={statistics?.currently_served_count ?? "—"} subtitle="Tokens currently in Served status" icon={Check} tone="amber" />
            </div>
            <Card className="mt-3">
              <CardContent className="flex flex-col gap-2 p-4 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="text-sm font-semibold text-foreground">Historical service record</p>
                  <p className="mt-1 text-xs text-muted-foreground">Visitors with a recorded served_at timestamp; distinct from current Served tokens.</p>
                </div>
                <Badge>{statistics?.historically_served_count ?? "—"} historically served</Badge>
              </CardContent>
            </Card>
          </section>

          <section aria-label="Queue overview">
            <SectionTitle
              action={
                <div className="grid grid-cols-2 gap-2 sm:flex">
                  <FilterSelect label="Service" onChange={setServiceFilter} value={serviceFilter}>
                    <option value="All">All services</option>
                    {SERVICE_TYPES.map((service) => <option key={service} value={service}>{service}</option>)}
                  </FilterSelect>
                  <FilterSelect label="Status" onChange={setStatusFilter} value={statusFilter}>
                    <option value="All">All statuses</option>
                    {TOKEN_STATUSES.map((status) => <option key={status} value={status}>{status}</option>)}
                  </FilterSelect>
                </div>
              }
              detail="Review tokens and advance them through the supported queue workflow."
              eyebrow="LIVE QUEUE"
              title="Current queue overview"
            />
            {errors.tokens && <ResourceError message={errors.tokens} onRetry={() => void refreshDashboard()} />}
            {!errors.tokens && tokens.length > 0 && (
              <p className="mb-3 text-xs text-muted-foreground">
                Visitor names are not included in the existing admin token-list API response.
              </p>
            )}
            <Card>
              {filteredTokens.length === 0 ? (
                <CardContent><EmptyState>{tokens.length ? "No tokens match these filters." : "There are no queue tokens yet."}</EmptyState></CardContent>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[760px] text-left text-sm">
                    <thead className="border-b border-border bg-background/70 text-xs text-muted-foreground">
                      <tr>
                        <th className="px-5 py-3 font-semibold">Token</th>
                        <th className="px-5 py-3 font-semibold">Visitor</th>
                        <th className="px-5 py-3 font-semibold">Service</th>
                        <th className="px-5 py-3 font-semibold">Counter</th>
                        <th className="px-5 py-3 font-semibold">Status</th>
                        <th className="px-5 py-3 font-semibold">Created</th>
                        <th className="px-5 py-3 font-semibold">Next step</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {filteredTokens.map((token) => {
                        const nextStatuses = STATUS_TRANSITIONS[token.status];
                        const busy = busyTokens.includes(token.token_id);
                        return (
                          <tr key={token.token_id}>
                            <td className="px-5 py-3.5 font-semibold text-foreground">{token.token_number}</td>
                            <td className="px-5 py-3.5 text-muted-foreground">—</td>
                            <td className="px-5 py-3.5 text-foreground">{token.service_type}</td>
                            <td className="px-5 py-3.5 text-foreground">{token.counter_name}</td>
                            <td className="px-5 py-3.5"><StatusBadge status={token.status} /></td>
                            <td className="px-5 py-3.5 text-muted-foreground">{formatDate(token.created_at)}</td>
                            <td className="px-5 py-3.5">
                              <div className="flex gap-1.5">
                                {nextStatuses.map((nextStatus) => (
                                  <Button
                                    className="min-h-8 px-2.5 py-1 text-xs"
                                    disabled={busy}
                                    key={nextStatus}
                                    onClick={() => void handleTokenStatus(token, nextStatus)}
                                    variant="secondary"
                                  >
                                    {busy ? <LoaderCircle aria-hidden="true" className="animate-spin" size={13} /> : null}
                                    {nextStatus}
                                  </Button>
                                ))}
                                {!nextStatuses.length && <span className="text-xs text-muted-foreground">Complete</span>}
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          </section>

          <section aria-label="Counter waiting-time estimates">
            <SectionTitle
              detail="Current model estimates for active counters. Estimates are unavailable when the backend cannot produce a valid prediction."
              eyebrow="MODEL ESTIMATES"
              title="Counter waiting times"
            />
            {errors.estimates && <ResourceError message={errors.estimates} onRetry={() => void refreshDashboard()} />}
            {!errors.estimates && recommendedCounterId !== null && (
              <div className="mb-4 flex items-start gap-3 rounded-xl border border-accent/25 bg-soft-accent p-4">
                <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-accent text-slate-950"><Check aria-hidden="true" size={18} /></span>
                <div>
                  <p className="text-sm font-semibold text-foreground">Recommended counter</p>
                  <p className="mt-1 text-sm text-muted-foreground">The backend recommends the available counter with the lowest valid prediction.</p>
                </div>
              </div>
            )}
            {!errors.estimates && recommendedCounterId === null && estimates.length > 0 && (
              <p className="mb-4 rounded-xl border border-border bg-background px-4 py-3 text-sm text-muted-foreground">
                No counter recommendation is available. The backend requires valid estimates for all active counters.
              </p>
            )}
            {!errors.estimates && estimates.length === 0 ? (
              <Card><CardContent><EmptyState>No active counters are available for estimates.</EmptyState></CardContent></Card>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {estimates.map((estimate) => (
                  <EstimateCard estimate={estimate} isRecommended={estimate.counter_id === recommendedCounterId} key={estimate.counter_id} />
                ))}
              </div>
            )}
          </section>

          <section aria-label="Counter management">
            <SectionTitle
              action={<Button onClick={openAddDialog}><Plus aria-hidden="true" size={17} />Add counter</Button>}
              detail="Configure the service counters available to visitors."
              eyebrow="SERVICE OPERATIONS"
              title="Service counters"
            />
            {errors.counters && <ResourceError message={errors.counters} onRetry={() => void refreshDashboard()} />}
            {counters.length === 0 ? (
              <Card><CardContent><EmptyState>No counters have been configured yet. Add one to get started.</EmptyState></CardContent></Card>
            ) : (
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {counters.map((counter) => (
                  <CounterCard
                    busy={busyCounters.includes(counter.counter_id)}
                    counter={counter}
                    key={counter.counter_id}
                    onEdit={() => openEditDialog(counter)}
                    onToggle={() => void handleCounterStatus(counter)}
                  />
                ))}
              </div>
            )}
          </section>
        </div>
      )}

      {dialog && (
        <CounterDialogView
          dialog={dialog}
          form={form}
          onChange={setForm}
          onClose={() => {
            if (!savingCounter) {
              setDialog(null);
              setActionError("");
            }
          }}
          onSubmit={(event) => void handleCounterSubmit(event)}
          saving={savingCounter}
          error={actionError}
        />
      )}
    </>
  );
}

function ResourceError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="mb-4 flex flex-col gap-3 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3.5 text-sm text-foreground sm:flex-row sm:items-center sm:justify-between" role="alert">
      <span>{message}</span>
      <Button className="shrink-0" onClick={onRetry} variant="secondary"><RefreshCw aria-hidden="true" size={15} />Retry</Button>
    </div>
  );
}

function CounterCard({
  counter,
  busy,
  onEdit,
  onToggle,
}: {
  counter: AdminCounter;
  busy: boolean;
  onEdit: () => void;
  onToggle: () => void;
}) {
  return (
    <Card>
      <CardContent className="p-4 sm:p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 className="truncate font-semibold text-foreground">{counter.counter_name}</h3>
            <p className="mt-1 text-sm text-muted-foreground">{counter.service_type}</p>
          </div>
          <StatusBadge status={counter.is_active ? "Active" : "Inactive"} />
        </div>
        <div className="mt-4 grid grid-cols-3 gap-2 border-y border-border py-3 text-center">
          <div><p className="text-lg font-semibold text-foreground">{counter.people_waiting}</p><p className="text-[11px] text-muted-foreground">Waiting</p></div>
          <div><p className="text-lg font-semibold text-foreground">{counter.active_counters}</p><p className="text-[11px] text-muted-foreground">Stations</p></div>
          <div><p className="text-lg font-semibold text-foreground">{counter.avg_service_time}m</p><p className="text-[11px] text-muted-foreground">Avg. service</p></div>
        </div>
        <div className="mt-3 flex gap-2">
          <Button className="flex-1" onClick={onEdit} variant="secondary"><Pencil aria-hidden="true" size={15} />Edit settings</Button>
          <Button className="flex-1" disabled={busy} onClick={onToggle} variant="ghost">
            {busy ? <LoaderCircle aria-hidden="true" className="animate-spin" size={15} /> : counter.is_active ? <ArrowDownRight aria-hidden="true" size={15} /> : <ArrowUpRight aria-hidden="true" size={15} />}
            {counter.is_active ? "Deactivate" : "Activate"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function EstimateCard({
  estimate,
  isRecommended,
}: {
  estimate: CounterEstimate;
  isRecommended: boolean;
}) {
  return (
    <Card className={isRecommended ? "border-accent/50 ring-1 ring-accent/20" : ""}>
      <CardContent className="p-4 sm:p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 className="truncate font-semibold text-foreground">{estimate.counter_name}</h3>
            <p className="mt-1 text-sm text-muted-foreground">{estimate.service_type}</p>
          </div>
          {isRecommended && <Badge className="shrink-0">Recommended</Badge>}
        </div>
        <div className="mt-5 flex items-end justify-between">
          <div>
            <p className="text-xs text-muted-foreground">Predicted wait</p>
            <p className="mt-1 text-2xl font-semibold text-foreground">
              {estimate.available && estimate.predicted_wait_minutes !== null
                ? `${formatMinutes(estimate.predicted_wait_minutes)} min`
                : "Unavailable"}
            </p>
          </div>
          <Clock3 aria-hidden="true" className="mb-1 text-accent" size={20} />
        </div>
      </CardContent>
    </Card>
  );
}

function CounterDialogView({
  dialog,
  form,
  onChange,
  onClose,
  onSubmit,
  saving,
  error,
}: {
  dialog: Exclude<CounterDialog, null>;
  form: CounterFormState;
  onChange: (state: CounterFormState) => void;
  onClose: () => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  saving: boolean;
  error: string;
}) {
  const editing = dialog.mode === "edit";
  const fieldClass = "mt-1.5 min-h-11 w-full rounded-xl border border-border bg-background px-3.5 text-sm text-foreground";
  return (
    <div
      className="fixed inset-0 z-[70] flex items-end justify-center bg-slate-950/55 p-0 backdrop-blur-sm sm:items-center sm:p-5"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section aria-labelledby="counter-dialog-title" aria-modal="true" className="surface-card max-h-[92vh] w-full overflow-y-auto rounded-t-2xl p-5 sm:max-w-xl sm:rounded-2xl sm:p-7" role="dialog">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs font-bold tracking-[0.15em] text-accent uppercase">COUNTER SETTINGS</p>
            <h2 className="mt-1 text-xl font-semibold text-foreground" id="counter-dialog-title">{editing ? "Update counter" : "Add a counter"}</h2>
            <p className="mt-1 text-sm text-muted-foreground">{editing ? "Counter name and service type are read-only in the existing API." : "Create a new service counter."}</p>
          </div>
          <Button aria-label="Close dialog" onClick={onClose} size="icon" variant="ghost"><X aria-hidden="true" size={18} /></Button>
        </div>
        {error && <p className="mt-4 rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-700 dark:text-red-200" role="alert">{error}</p>}
        <form className="mt-5 space-y-4" onSubmit={onSubmit}>
          {!editing && (
            <>
              <label className="block text-sm font-medium text-foreground">
                Counter name
                <input className={fieldClass} maxLength={100} minLength={1} onChange={(event) => onChange({ ...form, counter_name: event.target.value })} required value={form.counter_name} />
              </label>
              <label className="block text-sm font-medium text-foreground">
                Service type
                <select className={fieldClass} onChange={(event) => onChange({ ...form, service_type: event.target.value as ServiceType })} value={form.service_type}>
                  {SERVICE_TYPES.map((service) => <option key={service} value={service}>{service}</option>)}
                </select>
              </label>
            </>
          )}
          {editing && (
            <div className="grid gap-3 rounded-xl border border-border bg-background p-3 sm:grid-cols-2">
              <div><p className="text-xs text-muted-foreground">Counter</p><p className="mt-1 text-sm font-medium text-foreground">{dialog.counter.counter_name}</p></div>
              <div><p className="text-xs text-muted-foreground">Service</p><p className="mt-1 text-sm font-medium text-foreground">{dialog.counter.service_type}</p></div>
            </div>
          )}
          {editing && (
            <label className="block text-sm font-medium text-foreground">
              People waiting
              <input className={fieldClass} max={50} min={0} onChange={(event) => onChange({ ...form, people_waiting: event.target.value })} required type="number" value={form.people_waiting} />
            </label>
          )}
          <label className="block text-sm font-medium text-foreground">
            Active service stations
            <input className={fieldClass} max={5} min={1} onChange={(event) => onChange({ ...form, active_counters: event.target.value })} required type="number" value={form.active_counters} />
          </label>
          <label className="block text-sm font-medium text-foreground">
            Average service time (minutes)
            <input className={fieldClass} max={15} min={1} onChange={(event) => onChange({ ...form, avg_service_time: event.target.value })} required step="any" type="number" value={form.avg_service_time} />
          </label>
          <div className="flex flex-col-reverse gap-2 pt-2 sm:flex-row sm:justify-end">
            <Button disabled={saving} onClick={onClose} variant="secondary">Cancel</Button>
            <Button disabled={saving} type="submit">
              {saving ? <LoaderCircle aria-hidden="true" className="animate-spin" size={16} /> : <Check aria-hidden="true" size={16} />}
              {saving ? "Saving..." : editing ? "Save changes" : "Create counter"}
            </Button>
          </div>
        </form>
      </section>
    </div>
  );
}

function formatMinutes(minutes: number): string {
  return Number.isInteger(minutes) ? String(minutes) : minutes.toFixed(1);
}

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
}
