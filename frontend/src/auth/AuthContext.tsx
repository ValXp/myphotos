import { createContext, useContext, useEffect, useState } from "react";

export type AuthStatus = "checking" | "authenticated" | "unauthenticated";

interface AuthContextValue {
  status: AuthStatus;
  signIn: () => void;
  signOut: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);
const STORAGE_KEY = "myphotos_owner_session";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("checking");

  useEffect(() => {
    const stored = sessionStorage.getItem(STORAGE_KEY);
    setStatus(stored === "true" ? "authenticated" : "unauthenticated");
  }, []);

  const signIn = () => {
    sessionStorage.setItem(STORAGE_KEY, "true");
    setStatus("authenticated");
  };

  const signOut = () => {
    sessionStorage.removeItem(STORAGE_KEY);
    setStatus("unauthenticated");
  };

  return (
    <AuthContext.Provider value={{ status, signIn, signOut }}>
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
