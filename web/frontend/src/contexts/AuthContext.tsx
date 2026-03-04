import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { authApi, type UserProfile } from '../api/endpoints';
import { hasPermission, type RoleLevel } from '../utils/permissions';

interface AuthContextValue {
  user: UserProfile | null;
  loading: boolean;
  setUser: React.Dispatch<React.SetStateAction<UserProfile | null>>;
  refreshProfile: () => Promise<void>;
  /** Active guild ID (may be "*" for bot owners in "All Guilds" mode) */
  activeGuildId: string | null;
  /** Check if current user meets a minimum role level in the active guild */
  userHasPermission: (required: RoleLevel) => boolean;
  /** Current user's role level in the active guild */
  getUserRoleLevel: () => RoleLevel;
}

const AuthContext = createContext<AuthContextValue | null>(null);

/**
 * Hook to consume auth context.
 *
 * Must be used inside <AuthProvider>.
 */
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within <AuthProvider>');
  return ctx;
}

/**
 * Auth provider — fetches /auth/me on mount and exposes user state
 * + permission helpers to the entire component tree.
 */
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshProfile = useCallback(async () => {
    try {
      const data = await authApi.getMe();
      setUser(data.user);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshProfile();
  }, [refreshProfile]);

  const activeGuildId = user?.active_guild_id ?? null;

  const getUserRoleLevel = useCallback((): RoleLevel => {
    if (!user?.active_guild_id) return 'user';
    const perm = user.authorized_guilds[user.active_guild_id];
    return perm?.role_level || 'user';
  }, [user]);

  const userHasPermission = useCallback(
    (required: RoleLevel): boolean => hasPermission(getUserRoleLevel(), required),
    [getUserRoleLevel],
  );

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        setUser,
        refreshProfile,
        activeGuildId,
        userHasPermission,
        getUserRoleLevel,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
