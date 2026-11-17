import {
  Activity,
  BarChart3,
  ChevronLeft,
  CircleHelp,
  Home,
  KeyRound,
  LayoutDashboard,
  PanelLeftClose,
  PanelLeftOpen,
  UsersRound,
  X,
} from "lucide-react";
import { NavLink } from "react-router-dom";
import { Button } from "../ui/button";
import { useAuth } from "../auth/AuthProvider";

interface SidebarProps {
  collapsed: boolean;
  mobileOpen: boolean;
  onCollapse: () => void;
  onCloseMobile: () => void;
}

export function Sidebar({
  collapsed,
  mobileOpen,
  onCollapse,
  onCloseMobile,
}: SidebarProps) {
  const { state } = useAuth();
  const navigation = [
    { label: "Home", to: "/", icon: Home, end: true },
    { label: "Visitor Portal", to: "/visitor", icon: UsersRound },
    ...(state.status === "authenticated"
      ? [
          { label: "Admin Dashboard", to: "/admin", icon: LayoutDashboard },
          { label: "Analytics", to: "/analytics", icon: BarChart3 },
        ]
      : [{ label: "Admin sign in", to: "/admin/login", icon: KeyRound }]),
  ];

  return (
    <>
      {mobileOpen && (
        <button
          aria-label="Close navigation"
          className="fixed inset-0 z-40 bg-slate-950/45 lg:hidden"
          onClick={onCloseMobile}
        />
      )}
      <aside
        className={`sidebar fixed inset-y-0 left-0 z-50 flex w-[min(84vw,280px)] flex-col border-r border-border transition-[width,transform] duration-200 lg:sticky lg:top-0 lg:h-screen lg:translate-x-0 ${collapsed ? "lg:w-[84px]" : "lg:w-64"} ${mobileOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}`}
      >
        <div className="flex h-[76px] items-center justify-between border-b border-border px-5">
          <NavLink
            aria-label="SmartQueue home"
            className="flex min-w-0 items-center gap-3"
            onClick={onCloseMobile}
            to="/"
          >
            <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-accent text-slate-950 shadow-sm">
              <Activity aria-hidden="true" size={21} strokeWidth={2.5} />
            </span>
            <span className={`min-w-0 ${collapsed ? "lg:hidden" : ""}`}>
              <span className="block truncate text-base font-bold tracking-tight text-foreground">
                SmartQueue
              </span>
              <span className="block truncate text-[11px] text-muted-foreground">
                Queue intelligence
              </span>
            </span>
          </NavLink>
          <Button
            aria-label="Close navigation"
            className="text-foreground lg:hidden"
            onClick={onCloseMobile}
            size="icon"
            variant="ghost"
          >
            <X aria-hidden="true" size={18} />
          </Button>
          <Button
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className="hidden text-foreground lg:inline-flex"
            onClick={onCollapse}
            size="icon"
            variant="ghost"
          >
            {collapsed ? (
              <PanelLeftOpen aria-hidden="true" size={18} />
            ) : (
              <PanelLeftClose aria-hidden="true" size={18} />
            )}
          </Button>
        </div>

        <div className="px-3 pt-7">
          <p
            className={`px-3 pb-3 text-[10px] font-bold tracking-[0.17em] text-muted-foreground uppercase ${collapsed ? "lg:hidden" : ""}`}
          >
            Workspace
          </p>
          <nav aria-label="Main navigation" className="space-y-1">
            {navigation.map(({ label, to, icon: Icon, end }) => (
              <NavLink
                aria-label={collapsed ? label : undefined}
                className="sidebar-link flex min-h-11 items-center gap-3 rounded-xl px-3 text-sm"
                end={end}
                key={to}
                onClick={onCloseMobile}
                to={to}
              >
                <Icon aria-hidden="true" className="shrink-0" size={19} />
                <span className={`truncate ${collapsed ? "lg:hidden" : ""}`}>
                  {label}
                </span>
              </NavLink>
            ))}
          </nav>
        </div>

        <div className="mt-auto p-3">
          <div
            className={`rounded-2xl border border-border bg-background/70 p-3 ${collapsed ? "lg:hidden" : ""}`}
          >
            <span className="flex size-8 items-center justify-center rounded-lg bg-soft-accent text-accent">
              <CircleHelp aria-hidden="true" size={17} />
            </span>
            <p className="mt-3 text-xs font-semibold text-foreground">
              Need a hand?
            </p>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">
              SmartQueue keeps the next step clear.
            </p>
          </div>
          <div className="mt-4 flex items-center justify-between px-3 text-[11px] text-muted-foreground">
            <span className={collapsed ? "lg:hidden" : ""}>
              © 2026 SmartQueue
            </span>
            <ChevronLeft aria-hidden="true" className="hidden lg:block" size={14} />
          </div>
        </div>
      </aside>
    </>
  );
}
