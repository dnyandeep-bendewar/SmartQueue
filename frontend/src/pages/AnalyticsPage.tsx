import axios from "axios";
import {
  Activity,
  AlertCircle,
  BarChart3,
  Clock3,
  LoaderCircle,
  RefreshCw,
  Users,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card, CardContent } from "../components/ui/card";
import {
  fetchAnalyticsCounterEstimates,
  fetchAnalyticsOverview,
  fetchDailyTrends,
  fetchServiceBreakdown,
  fetchWaitingTimes,
  type AnalyticsOverview,
  type CounterEstimate,
  type DailyTrend,
  type ServiceBreakdownItem,
  type WaitingTimeObservation,
} from "../services/analytics";

interface AnalyticsErrors {
  overview?: string;
  dailyTrends?: string;
  serviceBreakdown?: string;
  waitingTimes?: string;
  counterEstimates?: string;
}

const SERVICE_COLORS = ["#0d9488", "#3b82f6", "#8b5cf6", "#f59e0b"];

function friendlyError(error: unknown): string {
  if (!axios.isAxiosError(error)) {
    return "Analytics could not be loaded. Please try again.";
  }
  if (!error.response) {
    return "Could not reach SmartQueue. Check the backend connection and retry.";
  }
  if (error.response.status === 401) {
    return "Your administrator session has expired. Sign in again to continue.";
  }
  if (error.response.status === 403) {
    return "Your session could not be verified. Refresh the page and try again.";
  }
  return error.response.status >= 500
    ? "Analytics are temporarily unavailable. Please try again shortly."
    : "Analytics could not be loaded. Please try again.";
}

function MetricCard({
  title,
  value,
  subtitle,
  icon: Icon,
  color,
}: {
  title: string;
  value: string | number;
  subtitle: string;
  icon: typeof Users;
  color: string;
}) {
  return (
    <Card>
      <CardContent className="p-4 sm:p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-sm font-medium text-muted-foreground">{title}</p>
            <p className="mt-2 text-3xl font-semibold tracking-tight text-foreground">
              {value}
            </p>
          </div>
          <span
            className="flex size-10 shrink-0 items-center justify-center rounded-xl"
            style={{ backgroundColor: `${color}1a`, color }}
          >
            <Icon aria-hidden="true" size={19} />
          </span>
        </div>
        <p className="mt-3 text-xs text-muted-foreground">{subtitle}</p>
      </CardContent>
    </Card>
  );
}

function SectionHeader({
  eyebrow,
  title,
  detail,
  trailing,
}: {
  eyebrow: string;
  title: string;
  detail: string;
  trailing?: React.ReactNode;
}) {
  return (
    <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <p className="text-[11px] font-bold tracking-[0.15em] text-accent uppercase">
          {eyebrow}
        </p>
        <h2 className="mt-1 text-xl font-semibold text-foreground">{title}</h2>
        <p className="mt-1 text-sm leading-6 text-muted-foreground">{detail}</p>
      </div>
      {trailing}
    </div>
  );
}

function EmptyState({ children }: { children: string }) {
  return (
    <div className="rounded-xl border border-dashed border-border px-4 py-9 text-center text-sm text-muted-foreground">
      {children}
    </div>
  );
}

function ResourceError({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div
      className="mb-4 flex flex-col gap-3 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3.5 text-sm text-foreground sm:flex-row sm:items-center sm:justify-between"
      role="alert"
    >
      <span className="flex items-center gap-2">
        <AlertCircle aria-hidden="true" className="shrink-0 text-amber-600" size={17} />
        {message}
      </span>
      <Button className="shrink-0" onClick={onRetry} variant="secondary">
        <RefreshCw aria-hidden="true" size={15} />
        Retry
      </Button>
    </div>
  );
}

function DailyTrendChart({ trends }: { trends: DailyTrend[] }) {
  if (!trends.length) {
    return <EmptyState>No historical served-token activity is recorded yet.</EmptyState>;
  }

  const width = 720;
  const height = 260;
  const margin = { top: 20, right: 20, bottom: 42, left: 42 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const maxValue = Math.max(1, ...trends.map((item) => item.visitor_count));
  const x = (index: number) =>
    margin.left +
    (trends.length === 1 ? plotWidth / 2 : (index / (trends.length - 1)) * plotWidth);
  const y = (value: number) => margin.top + plotHeight - (value / maxValue) * plotHeight;
  const path = trends
    .map((item, index) => `${index === 0 ? "M" : "L"} ${x(index)} ${y(item.visitor_count)}`)
    .join(" ");
  const tickIndexes = [...new Set([0, Math.floor((trends.length - 1) / 2), trends.length - 1])];

  return (
    <div className="w-full overflow-x-auto">
      <svg
        aria-label="Daily historically served visitors trend"
        className="h-auto min-w-[560px]"
        role="img"
        viewBox={`0 0 ${width} ${height}`}
      >
        {[0, 0.5, 1].map((fraction) => {
          const value = Math.round(maxValue * fraction);
          const lineY = y(value);
          return (
            <g key={fraction}>
              <line
                stroke="var(--border)"
                strokeDasharray="4 5"
                x1={margin.left}
                x2={width - margin.right}
                y1={lineY}
                y2={lineY}
              />
              <text
                fill="var(--muted-foreground)"
                fontSize="11"
                textAnchor="end"
                x={margin.left - 10}
                y={lineY + 4}
              >
                {value}
              </text>
            </g>
          );
        })}
        <path d={path} fill="none" stroke="var(--accent)" strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" />
        {trends.map((item, index) => (
          <circle
            cx={x(index)}
            cy={y(item.visitor_count)}
            fill="var(--surface)"
            key={`${item.served_date}-${index}`}
            r="4"
            stroke="var(--accent)"
            strokeWidth="2"
          >
            <title>{`${formatDate(item.served_date)}: ${item.visitor_count} visitors`}</title>
          </circle>
        ))}
        {tickIndexes.map((index) => (
          <text
            fill="var(--muted-foreground)"
            fontSize="11"
            key={index}
            textAnchor={index === 0 ? "start" : index === trends.length - 1 ? "end" : "middle"}
            x={x(index)}
            y={height - 13}
          >
            {formatDate(trends[index].served_date)}
          </text>
        ))}
      </svg>
    </div>
  );
}

function ServiceBreakdownChart({
  breakdown,
}: {
  breakdown: ServiceBreakdownItem[];
}) {
  const services = useMemo(() => {
    const counts = new Map<string, number>();
    breakdown.forEach((item) =>
      counts.set(item.service_type, (counts.get(item.service_type) ?? 0) + item.token_count),
    );
    return [...counts.entries()].map(([service_type, token_count]) => ({
      service_type,
      token_count,
    }));
  }, [breakdown]);
  const total = services.reduce((sum, item) => sum + item.token_count, 0);

  if (total === 0) {
    return <EmptyState>No token distribution is available yet.</EmptyState>;
  }

  let cumulative = 0;
  const stops = services.map((item, index) => {
    const start = cumulative;
    cumulative += (item.token_count / total) * 100;
    return `${SERVICE_COLORS[index % SERVICE_COLORS.length]} ${start}% ${cumulative}%`;
  });

  return (
    <div className="flex flex-col items-center gap-7 py-2 sm:flex-row sm:justify-center sm:gap-10">
      <div
        aria-label="Token distribution by service"
        className="relative size-48 shrink-0 rounded-full"
        role="img"
        style={{ background: `conic-gradient(${stops.join(", ")})` }}
      >
        <div className="absolute inset-5 flex flex-col items-center justify-center rounded-full bg-surface">
          <span className="text-3xl font-semibold text-foreground">{total}</span>
          <span className="text-xs text-muted-foreground">total tokens</span>
        </div>
      </div>
      <div className="w-full max-w-sm space-y-3">
        {services.map((item, index) => (
          <div className="flex items-center justify-between gap-4" key={item.service_type}>
            <div className="flex min-w-0 items-center gap-2.5">
              <span
                aria-hidden="true"
                className="size-2.5 shrink-0 rounded-full"
                style={{ backgroundColor: SERVICE_COLORS[index % SERVICE_COLORS.length] }}
              />
              <span className="truncate text-sm text-foreground">{item.service_type}</span>
            </div>
            <span className="text-sm font-semibold text-foreground">
              {item.token_count}
              <span className="ml-1.5 text-xs font-normal text-muted-foreground">
                ({Math.round((item.token_count / total) * 100)}%)
              </span>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function WaitingTimeChart({
  observations,
}: {
  observations: WaitingTimeObservation[];
}) {
  if (!observations.length) {
    return <EmptyState>No complete historical actual-versus-predicted observations are available.</EmptyState>;
  }

  const width = 720;
  const height = 280;
  const margin = { top: 18, right: 18, bottom: 42, left: 48 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const maxValue = Math.max(
    1,
    ...observations.flatMap((item) => [
      item.actual_waiting_time,
      item.predicted_waiting_time,
    ]),
  );
  const x = (index: number) =>
    margin.left +
    (observations.length === 1
      ? plotWidth / 2
      : (index / (observations.length - 1)) * plotWidth);
  const y = (value: number) => margin.top + plotHeight - (value / maxValue) * plotHeight;
  const makePath = (key: "actual_waiting_time" | "predicted_waiting_time") =>
    observations
      .map((item, index) => `${index === 0 ? "M" : "L"} ${x(index)} ${y(item[key])}`)
      .join(" ");
  const tickIndexes = [...new Set([0, Math.floor((observations.length - 1) / 2), observations.length - 1])];

  return (
    <>
      <div className="mb-4 flex flex-wrap gap-4 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-2">
          <span className="h-0.5 w-5 rounded bg-accent" /> Actual
        </span>
        <span className="inline-flex items-center gap-2">
          <span className="h-0.5 w-5 rounded bg-blue-500" /> Predicted
        </span>
      </div>
      <div className="w-full overflow-x-auto">
        <svg
          aria-label="Historical actual and predicted waiting-time observations"
          className="h-auto min-w-[560px]"
          role="img"
          viewBox={`0 0 ${width} ${height}`}
        >
          {[0, 0.5, 1].map((fraction) => {
            const value = Number((maxValue * fraction).toFixed(1));
            const lineY = y(value);
            return (
              <g key={fraction}>
                <line
                  stroke="var(--border)"
                  strokeDasharray="4 5"
                  x1={margin.left}
                  x2={width - margin.right}
                  y1={lineY}
                  y2={lineY}
                />
                <text fill="var(--muted-foreground)" fontSize="11" textAnchor="end" x={margin.left - 9} y={lineY + 4}>
                  {value}m
                </text>
              </g>
            );
          })}
          <path d={makePath("actual_waiting_time")} fill="none" stroke="var(--accent)" strokeLinecap="round" strokeWidth="2.5" />
          <path d={makePath("predicted_waiting_time")} fill="none" stroke="#3b82f6" strokeLinecap="round" strokeWidth="2.5" strokeDasharray="6 4" />
          {observations.map((item, index) => (
            <g key={`${item.recorded_at}-${index}`}>
              <circle cx={x(index)} cy={y(item.actual_waiting_time)} fill="var(--accent)" r="3.5">
                <title>{`Actual: ${item.actual_waiting_time} min`}</title>
              </circle>
              <circle cx={x(index)} cy={y(item.predicted_waiting_time)} fill="#3b82f6" r="3.5">
                <title>{`Predicted: ${item.predicted_waiting_time} min`}</title>
              </circle>
            </g>
          ))}
          {tickIndexes.map((index) => (
            <text
              fill="var(--muted-foreground)"
              fontSize="11"
              key={index}
              textAnchor={index === 0 ? "start" : index === observations.length - 1 ? "end" : "middle"}
              x={x(index)}
              y={height - 13}
            >
              {formatDateTime(observations[index].recorded_at)}
            </text>
          ))}
        </svg>
      </div>
    </>
  );
}

function formatDate(value: string): string {
  const date = new Date(`${value}T00:00:00`);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(date);
}

function formatDateTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(date);
}

function CounterEstimates({
  counters,
  recommendedCounterId,
}: {
  counters: CounterEstimate[];
  recommendedCounterId: number | null;
}) {
  if (!counters.length) {
    return <EmptyState>No active counters are available for model-based estimates.</EmptyState>;
  }
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {counters.map((counter) => {
        const recommended = counter.counter_id === recommendedCounterId;
        return (
          <Card className={recommended ? "border-accent/50 ring-1 ring-accent/20" : ""} key={counter.counter_id}>
            <CardContent className="p-4 sm:p-5">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h3 className="truncate font-semibold text-foreground">{counter.counter_name}</h3>
                  <p className="mt-1 text-sm text-muted-foreground">{counter.service_type}</p>
                </div>
                {recommended && <Badge className="shrink-0">Recommended</Badge>}
              </div>
              <div className="mt-5 flex items-end justify-between">
                <div>
                  <p className="text-xs text-muted-foreground">Predicted waiting time</p>
                  <p className="mt-1 text-2xl font-semibold text-foreground">
                    {counter.available && counter.predicted_wait_minutes !== null
                        ? `${formatMinutes(counter.predicted_wait_minutes)} min`
                      : "Unavailable"}
                  </p>
                </div>
                <Clock3 aria-hidden="true" className="mb-1 text-accent" size={20} />
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

function formatMinutes(minutes: number): string {
  return Number.isInteger(minutes) ? String(minutes) : minutes.toFixed(1);
}

export function AnalyticsPage() {
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null);
  const [dailyTrends, setDailyTrends] = useState<DailyTrend[]>([]);
  const [serviceBreakdown, setServiceBreakdown] = useState<ServiceBreakdownItem[]>([]);
  const [waitingTimes, setWaitingTimes] = useState<WaitingTimeObservation[]>([]);
  const [waitingTimeSufficient, setWaitingTimeSufficient] = useState(false);
  const [excludedObservations, setExcludedObservations] = useState(0);
  const [estimates, setEstimates] = useState<CounterEstimate[]>([]);
  const [recommendedCounterId, setRecommendedCounterId] = useState<number | null>(null);
  const [errors, setErrors] = useState<AnalyticsErrors>({});
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const refreshAnalytics = useCallback(async () => {
    setRefreshing(true);
    const results = await Promise.allSettled([
      fetchAnalyticsOverview(),
      fetchDailyTrends(),
      fetchServiceBreakdown(),
      fetchWaitingTimes(),
      fetchAnalyticsCounterEstimates(),
    ]);
    const nextErrors: AnalyticsErrors = {};
    const [overviewResult, trendsResult, breakdownResult, waitingResult, estimatesResult] =
      results;

    if (overviewResult.status === "fulfilled") {
      setOverview(overviewResult.value);
    } else {
      nextErrors.overview = friendlyError(overviewResult.reason);
    }
    if (trendsResult.status === "fulfilled") {
      setDailyTrends(trendsResult.value.trends);
    } else {
      nextErrors.dailyTrends = friendlyError(trendsResult.reason);
    }
    if (breakdownResult.status === "fulfilled") {
      setServiceBreakdown(breakdownResult.value.breakdown);
    } else {
      nextErrors.serviceBreakdown = friendlyError(breakdownResult.reason);
    }
    if (waitingResult.status === "fulfilled") {
      setWaitingTimes(waitingResult.value.observations);
      setWaitingTimeSufficient(waitingResult.value.sufficient_observations);
      setExcludedObservations(waitingResult.value.excluded_observation_count);
    } else {
      nextErrors.waitingTimes = friendlyError(waitingResult.reason);
    }
    if (estimatesResult.status === "fulfilled") {
      setEstimates(estimatesResult.value.counters);
      setRecommendedCounterId(estimatesResult.value.recommended_counter_id);
    } else {
      nextErrors.counterEstimates = friendlyError(estimatesResult.reason);
    }
    setErrors(nextErrors);
    setLoading(false);
    setRefreshing(false);
  }, []);

  useEffect(() => {
    void refreshAnalytics();
  }, [refreshAnalytics]);

  const totalTokens = overview
    ? overview.waiting_tokens +
      overview.serving_tokens +
      overview.currently_served_tokens
    : null;

  return (
    <>
      <PageHeader
        action={
          <Button
            disabled={refreshing}
            onClick={() => void refreshAnalytics()}
            variant="secondary"
          >
            {refreshing ? (
              <LoaderCircle aria-hidden="true" className="animate-spin" size={16} />
            ) : (
              <RefreshCw aria-hidden="true" size={16} />
            )}
            Refresh analytics
          </Button>
        }
        description="Understand service activity, queue outcomes, and recorded waiting-time performance."
        eyebrow="QUEUE INTELLIGENCE"
        title="Analytics Dashboard"
      />

      {loading ? (
        <LoadingState label="Loading SmartQueue analytics" />
      ) : (
        <div className="space-y-9">
          <section aria-label="Analytics overview">
            <div className="mb-4">
              <h2 className="text-lg font-semibold text-foreground">Service overview</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Live counts and historical served records from the backend.
              </p>
            </div>
            {errors.overview && (
              <ResourceError message={errors.overview} onRetry={() => void refreshAnalytics()} />
            )}
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <MetricCard
                color="#0d9488"
                icon={BarChart3}
                subtitle="Waiting, serving, and currently served statuses"
                title="Total tokens"
                value={totalTokens ?? "—"}
              />
              <MetricCard
                color="#f59e0b"
                icon={Users}
                subtitle={`${overview?.active_counters ?? "—"} active service counters`}
                title="Currently waiting"
                value={overview?.waiting_tokens ?? "—"}
              />
              <MetricCard
                color="#3b82f6"
                icon={Activity}
                subtitle="Tokens currently in Served status"
                title="Currently served"
                value={overview?.currently_served_tokens ?? "—"}
              />
              <MetricCard
                color="#8b5cf6"
                icon={Clock3}
                subtitle={`${overview?.total_counters ?? "—"} total counters`}
                title="Historically served"
                value={overview?.historically_served_visitors ?? "—"}
              />
            </div>
            {overview && (
              <p className="mt-3 text-xs text-muted-foreground">
                Current serving: {overview.serving_tokens}. Historical served counts are based on recorded completion times and are not added to current tokens.
              </p>
            )}
          </section>

          <div className="grid gap-6 xl:grid-cols-2">
            <section aria-label="Daily served visitor trends">
              <SectionHeader
                detail="Daily counts from historical served_at records, in chronological order."
                eyebrow="DAILY ACTIVITY"
                title="Served visitors over time"
              />
              {errors.dailyTrends ? (
                <ResourceError message={errors.dailyTrends} onRetry={() => void refreshAnalytics()} />
              ) : (
                <Card>
                  <CardContent>
                    <DailyTrendChart trends={dailyTrends} />
                  </CardContent>
                </Card>
              )}
            </section>

            <section aria-label="Token distribution by service">
              <SectionHeader
                detail="Token totals by service type, grouped from backend status counts."
                eyebrow="SERVICE MIX"
                title="Service breakdown"
              />
              {errors.serviceBreakdown ? (
                <ResourceError message={errors.serviceBreakdown} onRetry={() => void refreshAnalytics()} />
              ) : (
                <Card>
                  <CardContent>
                    <ServiceBreakdownChart breakdown={serviceBreakdown} />
                  </CardContent>
                </Card>
              )}
            </section>
          </div>

          <section aria-label="Historical waiting-time comparison">
            <SectionHeader
              detail="Recorded observations only. Actual and model-predicted values remain separate."
              eyebrow="WAITING-TIME ANALYSIS"
              title="Actual vs. predicted wait"
              trailing={
                !errors.waitingTimes && (
                  <Badge>
                    {waitingTimes.length} valid observations
                  </Badge>
                )
              }
            />
            {errors.waitingTimes ? (
              <ResourceError message={errors.waitingTimes} onRetry={() => void refreshAnalytics()} />
            ) : (
              <>
                {!waitingTimeSufficient && (
                  <div className="mb-4 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3.5 text-sm text-foreground">
                    Insufficient valid historical observations for a reliable comparison. At least two complete records are needed.
                  </div>
                )}
                {excludedObservations > 0 && (
                  <p className="mb-3 text-xs text-muted-foreground">
                    {excludedObservations} malformed or incomplete historical record{excludedObservations === 1 ? "" : "s"} excluded by the backend.
                  </p>
                )}
                <Card>
                  <CardContent>
                    <WaitingTimeChart observations={waitingTimes} />
                  </CardContent>
                </Card>
              </>
            )}
          </section>

          <section aria-label="Active counter estimates">
            <SectionHeader
              detail="Current model estimates for active counters. Unavailable predictions are shown as such."
              eyebrow="MODEL ESTIMATES"
              title="Counter waiting times"
              trailing={
                !errors.counterEstimates &&
                recommendedCounterId !== null && (
                  <Badge>Recommendation based on valid backend predictions</Badge>
                )
              }
            />
            {errors.counterEstimates ? (
              <ResourceError message={errors.counterEstimates} onRetry={() => void refreshAnalytics()} />
            ) : (
              <>
                {!recommendedCounterId && estimates.length > 0 && (
                  <p className="mb-4 rounded-xl border border-border bg-background px-4 py-3 text-sm text-muted-foreground">
                    No counter recommendation is available. The backend only recommends when all active counters have valid estimates.
                  </p>
                )}
                <CounterEstimates
                  counters={estimates}
                  recommendedCounterId={recommendedCounterId}
                />
              </>
            )}
          </section>
        </div>
      )}
    </>
  );
}
