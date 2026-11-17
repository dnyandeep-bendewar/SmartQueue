import { LogOut, Menu } from "lucide-react";
import { useState } from "react";
import { Outlet } from "react-router-dom";
import { ThemeToggle } from "./ThemeToggle";
import { Sidebar } from "./Sidebar";
import { Button } from "../ui/button";
import { useAuth } from "../auth/AuthProvider";
import axios from "axios";

export function AppLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [logoutError, setLogoutError] = useState("");
  const [loggingOut, setLoggingOut] = useState(false);
  const { state, logout } = useAuth();

  const handleLogout = async () => {
    setLoggingOut(true);
    setLogoutError("");
    try {
      await logout();
    } catch (error) {
      setLogoutError(
        axios.isAxiosError(error) && !error.response
          ? "Could not reach SmartQueue to sign out. Please retry."
          : "Sign out could not be completed. Please retry.",
      );
    } finally {
      setLoggingOut(false);
    }
  };

  return (
    <div className="app-shell flex min-h-screen">
      <Sidebar
        collapsed={collapsed}
        mobileOpen={mobileOpen}
        onCollapse={() => setCollapsed((value) => !value)}
        onCloseMobile={() => setMobileOpen(false)}
      />
      <div className="min-w-0 flex-1">
        <header className="sticky top-0 z-30 flex h-[76px] items-center justify-between border-b border-border bg-background/90 px-4 backdrop-blur-md sm:px-7 lg:px-10">
          <div className="flex min-w-0 items-center gap-3">
            <Button
              aria-label="Open navigation"
              className="shrink-0 text-foreground lg:hidden"
              onClick={() => setMobileOpen(true)}
              size="icon"
              variant="secondary"
            >
              <Menu aria-hidden="true" size={19} />
            </Button>
            <div className="hidden text-sm text-muted-foreground sm:block">
              Less waiting. <span className="text-foreground">Better experiences.</span>
            </div>
            <div className="text-sm font-semibold text-foreground sm:hidden">
              SmartQueue
            </div>
          </div>
          <div className="flex items-center gap-3">
            {state.status === "authenticated" && (
              <>
                <span className="hidden text-xs text-muted-foreground sm:block">
                  {state.username}
                </span>
                <Button
                  aria-label="Log out"
                  disabled={loggingOut}
                  onClick={() => void handleLogout()}
                  variant="secondary"
                >
                  {loggingOut ? (
                    <span className="size-4 animate-spin rounded-full border-2 border-current border-r-transparent" />
                  ) : (
                    <LogOut aria-hidden="true" size={16} />
                  )}
                  <span className="hidden sm:inline">
                    {loggingOut ? "Signing out..." : "Log out"}
                  </span>
                </Button>
              </>
            )}
            <span className="hidden text-xs text-muted-foreground md:block">
              A clearer queue starts here
            </span>
            <ThemeToggle />
          </div>
        </header>
        {logoutError && (
          <div
            className="mx-4 mt-4 rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-700 sm:mx-7 lg:mx-10 dark:text-red-200"
            role="alert"
          >
            <div className="flex items-center justify-between gap-3">
              <span>{logoutError}</span>
              <Button
                className="shrink-0"
                onClick={() => void handleLogout()}
                size="default"
                variant="secondary"
              >
                Retry
              </Button>
            </div>
          </div>
        )}
        <main className="mx-auto w-full max-w-[1440px] px-4 py-7 sm:px-7 sm:py-9 lg:px-10 lg:py-10">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
