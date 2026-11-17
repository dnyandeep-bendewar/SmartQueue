import axios from "axios";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  fetchAdminSession,
  loginAdmin,
  logoutAdmin,
  type AdminSession,
} from "../../services/auth";

export type AuthState =
  | { status: "checking" }
  | { status: "unauthenticated" }
  | { status: "error"; message: string }
  | {
      status: "authenticated";
      username: string;
      csrfToken: string;
    };

interface AuthContextValue {
  state: AuthState;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  checkSession: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function isUnauthorized(error: unknown): boolean {
  return axios.isAxiosError(error) && error.response?.status === 401;
}

function sessionFailureMessage(error: unknown): string {
  if (axios.isAxiosError(error) && !error.response) {
    return "SmartQueue could not be reached. Check the connection and try again.";
  }
  return "Your session could not be verified right now. Please try again.";
}

function authenticatedState(session: AdminSession): AuthState {
  return {
    status: "authenticated",
    username: session.username,
    csrfToken: session.csrf_token,
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: "checking" });

  const checkSession = useCallback(async () => {
    setState({ status: "checking" });
    try {
      setState(authenticatedState(await fetchAdminSession()));
    } catch (error) {
      if (isUnauthorized(error)) {
        setState({ status: "unauthenticated" });
      } else {
        setState({ status: "error", message: sessionFailureMessage(error) });
      }
    }
  }, []);

  useEffect(() => {
    void checkSession();
  }, [checkSession]);

  const login = useCallback(async (username: string, password: string) => {
    const session = await loginAdmin({ username, password });
    setState(authenticatedState(session));
  }, []);

  const logout = useCallback(async () => {
    if (state.status !== "authenticated") {
      setState({ status: "unauthenticated" });
      return;
    }

    try {
      await logoutAdmin(state.csrfToken);
      setState({ status: "unauthenticated" });
    } catch (error) {
      if (isUnauthorized(error)) {
        setState({ status: "unauthenticated" });
        return;
      }
      throw error;
    }
  }, [state]);

  const value = useMemo(
    () => ({ state, login, logout, checkSession }),
    [state, login, logout, checkSession],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider.");
  }
  return context;
}
