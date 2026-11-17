import {
  ArrowRight,
  ArrowUpRight,
  Check,
  Clock3,
  Compass,
  Layers3,
  ShieldCheck,
  Sparkles,
  UsersRound,
} from "lucide-react";
import { Link } from "react-router-dom";
import { Badge } from "../components/ui/badge";
import { Card, CardContent } from "../components/ui/card";

const workspaces = [
  {
    title: "Visitor Portal",
    description: "Find a service, check the queue, and plan your visit.",
    to: "/visitor",
    icon: UsersRound,
    label: "For visitors",
  },
  {
    title: "Admin Dashboard",
    description: "A focused space for service counters and queue operations.",
    to: "/admin",
    icon: Layers3,
    label: "For administrators",
  },
  {
    title: "Analytics",
    description: "Explore historical service trends and waiting-time insights.",
    to: "/analytics",
    icon: Compass,
    label: "For better decisions",
  },
];

const steps = [
  {
    number: "01",
    title: "Choose a service",
    description: "Select the college office service you need.",
  },
  {
    number: "02",
    title: "See your place",
    description: "Get a clear view of queue progress and estimated wait.",
  },
  {
    number: "03",
    title: "Arrive with a plan",
    description: "Use your time better while the queue moves forward.",
  },
];

const features = [
  {
    icon: Clock3,
    title: "More predictable visits",
    description:
      "Waiting-time estimates help visitors make more informed plans.",
  },
  {
    icon: ShieldCheck,
    title: "Clear queue updates",
    description:
      "Purpose-built workflows keep service status easy to understand.",
  },
  {
    icon: Sparkles,
    title: "Useful operational insight",
    description:
      "Historical trends can help teams understand how service is moving.",
  },
];

export function HomePage() {
  return (
    <div className="space-y-12 sm:space-y-16">
      <section className="hero-grid surface-card relative isolate overflow-hidden rounded-[28px] px-6 py-9 sm:px-10 sm:py-12 lg:px-14 lg:py-14">
        <div className="hero-orb pointer-events-none absolute -top-20 -right-20 -z-10 size-[360px] sm:size-[460px]" />
        <div className="max-w-3xl">
          <Badge>
            <span className="size-1.5 rounded-full bg-accent" />
            Smarter service, one step at a time
          </Badge>
          <h1 className="mt-6 max-w-2xl text-4xl leading-[1.08] font-semibold tracking-tight text-foreground sm:text-5xl lg:text-[60px]">
            Less waiting.
            <br />
            <span className="text-accent">Better experiences.</span>
          </h1>
          <p className="mt-5 max-w-xl text-base leading-7 text-muted-foreground sm:text-lg sm:leading-8">
            Welcome to SmartQueue — a more thoughtful way to navigate college
            service queues, with clearer updates for visitors and useful tools
            for the people who keep things moving.
          </p>
          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <Link
              className="group inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-accent px-5 py-2 text-sm font-semibold text-slate-950 transition-colors hover:bg-accent-hover"
              to="/visitor"
            >
              Open Visitor Portal
              <ArrowRight
                aria-hidden="true"
                className="transition-transform group-hover:translate-x-0.5"
                size={17}
              />
            </Link>
            <Link
              className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl border border-border bg-surface px-5 py-2 text-sm font-semibold text-foreground transition-colors hover:bg-background"
              to="/admin"
            >
              Explore the dashboard
            </Link>
          </div>
        </div>
        <div className="mt-10 grid max-w-2xl grid-cols-1 gap-3 border-t border-border/80 pt-6 sm:grid-cols-3">
          {[
            "Clearer queue journeys",
            "Thoughtful time estimates",
            "Useful service insights",
          ].map((item) => (
            <div className="flex items-center gap-2 text-xs text-muted-foreground" key={item}>
              <Check aria-hidden="true" className="shrink-0 text-accent" size={15} />
              {item}
            </div>
          ))}
        </div>
        <div className="pointer-events-none absolute right-8 bottom-8 hidden size-48 items-center justify-center rounded-full border border-accent/15 bg-surface/40 lg:flex">
          <div className="flex size-32 items-center justify-center rounded-full border border-accent/20 bg-surface/70 shadow-xl">
            <div className="flex size-20 items-center justify-center rounded-[26px] bg-accent text-slate-950 shadow-lg">
              <Clock3 aria-hidden="true" size={34} strokeWidth={1.8} />
            </div>
          </div>
        </div>
      </section>

      <section>
        <div className="mb-6">
          <p className="mb-2 text-xs font-bold tracking-[0.16em] text-accent uppercase">
            YOUR SMARTQUEUE WORKSPACE
          </p>
          <h2 className="text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
            A smoother way to serve
          </h2>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground sm:text-base">
            Start with the workspace that fits what you need to do.
          </p>
        </div>
        <div className="grid gap-4 md:grid-cols-3">
          {workspaces.map(({ title, description, to, icon: Icon, label }) => (
            <Link aria-label={`Open ${title}`} className="group block" key={to} to={to}>
              <Card className="h-full" interactive>
                <CardContent className="flex h-full flex-col">
                  <div className="flex items-start justify-between">
                    <span className="flex size-11 items-center justify-center rounded-xl bg-soft-accent text-accent">
                      <Icon aria-hidden="true" size={20} />
                    </span>
                    <ArrowUpRight
                      aria-hidden="true"
                      className="text-muted-foreground transition-colors group-hover:text-accent"
                      size={18}
                    />
                  </div>
                  <p className="mt-6 text-xs font-semibold tracking-wide text-accent uppercase">
                    {label}
                  </p>
                  <h3 className="mt-2 text-lg font-semibold text-foreground">
                    {title}
                  </h3>
                  <p className="mt-2 flex-1 text-sm leading-6 text-muted-foreground">
                    {description}
                  </p>
                  <span className="mt-5 inline-flex items-center gap-2 text-sm font-semibold text-foreground">
                    Open workspace
                    <ArrowRight
                      aria-hidden="true"
                      className="text-accent transition-transform group-hover:translate-x-1"
                      size={16}
                    />
                  </span>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      </section>

      <section className="grid gap-8 lg:grid-cols-[0.82fr_1.18fr] lg:gap-14">
        <div>
          <p className="mb-2 text-xs font-bold tracking-[0.16em] text-accent uppercase">
            A SIMPLE VISITOR JOURNEY
          </p>
          <h2 className="max-w-md text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
            From service to next step, made clearer.
          </h2>
          <p className="mt-4 max-w-md text-sm leading-7 text-muted-foreground">
            SmartQueue is designed to make the visit easier to understand, from
            choosing a service to knowing what to expect next.
          </p>
          <Link
            className="mt-6 inline-flex min-h-10 items-center justify-center gap-2 rounded-xl border border-border bg-surface px-4 py-2 text-sm font-semibold text-foreground transition-colors hover:bg-background"
            to="/visitor"
          >
              See the visitor experience
              <ArrowRight aria-hidden="true" size={16} />
          </Link>
        </div>
        <div className="space-y-3">
          {steps.map((step) => (
            <Card className="shadow-none" key={step.number}>
              <CardContent className="flex items-start gap-4 p-4 sm:gap-5 sm:p-5">
                <span className="step-number flex size-11 shrink-0 items-center justify-center rounded-xl text-sm font-bold">
                  {step.number}
                </span>
                <div>
                  <h3 className="font-semibold text-foreground">{step.title}</h3>
                  <p className="mt-1 text-sm leading-6 text-muted-foreground">
                    {step.description}
                  </p>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      <section>
        <div className="mb-6">
          <p className="mb-2 text-xs font-bold tracking-[0.16em] text-accent uppercase">
            DESIGNED AROUND THE EXPERIENCE
          </p>
          <h2 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
            Useful from the first interaction
          </h2>
        </div>
        <div className="grid gap-4 md:grid-cols-3">
          {features.map(({ icon: Icon, title, description }) => (
            <Card className="shadow-none" key={title}>
              <CardContent>
                <span className="flex size-10 items-center justify-center rounded-xl bg-soft-accent text-accent">
                  <Icon aria-hidden="true" size={19} />
                </span>
                <h3 className="mt-5 font-semibold text-foreground">{title}</h3>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">
                  {description}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>
    </div>
  );
}
