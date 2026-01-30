import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { fetchSessionStatus, logout } from "./webauthn";

export type AuthStatus = "checking" | "authenticated" | "unauthenticated";

interface AuthContextValue {
  status: AuthStatus;
  completeSignIn: () => void;
  signOut: () => Promise<void>;
  refreshSession: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("checking");

  const refreshSession = useCallback(async () => {
    try {
      const hasSession = await fetchSessionStatus();
      setStatus(hasSession ? "authenticated" : "unauthenticated");
    } catch (error) {
      console.warn("Session check failed.", error);
      setStatus("unauthenticated");
    }
  }, []);

  useEffect(() => {
    void refreshSession();
  }, [refreshSession]);

  const completeSignIn = () => {
    setStatus("authenticated");
  };

  const signOut = useCallback(async () => {
    try {
      await logout();
    } catch (error) {
      console.warn("Sign out failed.", error);
    } finally {
      setStatus("unauthenticated");
    }
  }, []);

  return (
    <AuthContext.Provider value={{ status, completeSignIn, signOut, refreshSession }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}
