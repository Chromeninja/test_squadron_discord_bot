import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import {
  ALL_GUILDS_SENTINEL,
  authApi,
  guildApi,
  type GuildInfo,
  type GuildSummary,
  type UserProfile,
} from '../../api/endpoints';
import { useClickOutside } from '../../hooks/useClickOutside';
import { useIsMobile } from '../../hooks/useMediaQuery';
import { cn } from '../../utils/cn';
import {
  getRoleDisplayName,
  hasPermission,
  type RoleLevel,
} from '../../utils/permissions';
import { handleApiError } from '../../utils/toast';

export interface DashboardShellProps {
  user: UserProfile;
  onUserChange: (user: UserProfile | null) => void;
  onRefreshProfile: () => Promise<void>;
}

interface SidebarItem {
  to: string;
  label: string;
  icon: ReactNode;
  visible: boolean;
  badge?: string | null;
}

interface SidebarSection {
  title: string;
  items: SidebarItem[];
}

function getDiscordAvatarUrl(user: UserProfile): string | null {
  if (!user.avatar) {
    return null;
  }

  if (user.avatar.startsWith('http://') || user.avatar.startsWith('https://')) {
    return user.avatar;
  }

  return `https://cdn.discordapp.com/avatars/${user.user_id}/${user.avatar}.png?size=128`;
}

function getInitials(label: string): string {
  const parts = label.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) {
    return '?';
  }
  if (parts.length === 1) {
    return parts[0].slice(0, 2).toUpperCase();
  }
  return `${parts[0][0] ?? ''}${parts[1][0] ?? ''}`.toUpperCase();
}

function DashboardIcon({ className = 'h-4 w-4' }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" fill="currentColor" className={className} aria-hidden="true">
      <path d="M2.5 2A1.5 1.5 0 0 0 1 3.5v3A1.5 1.5 0 0 0 2.5 8h3A1.5 1.5 0 0 0 7 6.5v-3A1.5 1.5 0 0 0 5.5 2h-3ZM10.5 2A1.5 1.5 0 0 0 9 3.5v1A1.5 1.5 0 0 0 10.5 6h3A1.5 1.5 0 0 0 15 4.5v-1A1.5 1.5 0 0 0 13.5 2h-3ZM10.5 8A1.5 1.5 0 0 0 9 9.5v3a1.5 1.5 0 0 0 1.5 1.5h3a1.5 1.5 0 0 0 1.5-1.5v-3A1.5 1.5 0 0 0 13.5 8h-3ZM2.5 10A1.5 1.5 0 0 0 1 11.5v1A1.5 1.5 0 0 0 2.5 14h3A1.5 1.5 0 0 0 7 12.5v-1A1.5 1.5 0 0 0 5.5 10h-3Z" />
    </svg>
  );
}

function MetricsIcon({ className = 'h-4 w-4' }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" fill="currentColor" className={className} aria-hidden="true">
      <path d="M2 13.25A.75.75 0 0 1 2.75 12.5h10.5a.75.75 0 0 1 0 1.5H2.75A.75.75 0 0 1 2 13.25ZM3 10.5A1.5 1.5 0 0 1 4.5 9h.25A1.25 1.25 0 0 1 6 10.25v1.5a.25.25 0 0 1-.25.25H4.5A1.5 1.5 0 0 1 3 10.5Zm3.5-3A1.5 1.5 0 0 1 8 6h.25A1.25 1.25 0 0 1 9.5 7.25v4.5a.25.25 0 0 1-.25.25H8A1.5 1.5 0 0 1 6.5 10.5v-3Zm3.5-3A1.5 1.5 0 0 1 11.5 3h.25A1.25 1.25 0 0 1 13 4.25v7.5a.25.25 0 0 1-.25.25H11.5A1.5 1.5 0 0 1 10 10.5v-6Z" />
    </svg>
  );
}

function UsersIcon({ className = 'h-4 w-4' }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" fill="currentColor" className={className} aria-hidden="true">
      <path d="M10.5 6A2.5 2.5 0 1 0 10.5 1a2.5 2.5 0 0 0 0 5ZM5.25 7A2.25 2.25 0 1 0 5.25 2.5 2.25 2.25 0 0 0 5.25 7Zm4.247.5h1.758A2.745 2.745 0 0 1 14 10.245V11a1 1 0 0 1-1 1H9.013c.156-.305.237-.645.237-1v-.755A3.232 3.232 0 0 0 7.945 7.5h1.552ZM2 10.25A2.75 2.75 0 0 1 4.75 7.5h1a2.75 2.75 0 0 1 2.75 2.75V11a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1v-.75Z" />
    </svg>
  );
}

function VoiceIcon({ className = 'h-4 w-4' }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" fill="currentColor" className={className} aria-hidden="true">
      <path d="M4.54 3.115A.75.75 0 0 1 5 3.81v8.38a.75.75 0 0 1-1.28.53L1.29 10.29A1 1 0 0 1 1 9.584V6.416a1 1 0 0 1 .29-.707L3.72 3.28a.75.75 0 0 1 .82-.165ZM10.72 4.47a.75.75 0 1 0-1.06 1.06A3.47 3.47 0 0 1 10.68 8c0 .95-.376 1.86-1.02 2.53a.75.75 0 0 0 1.08 1.04A5 5 0 0 0 12.18 8a4.97 4.97 0 0 0-1.46-3.53Zm2.72-2.22a.75.75 0 1 0-1.06 1.06A6.59 6.59 0 0 1 14.32 8a6.6 6.6 0 0 1-1.94 4.69.75.75 0 1 0 1.06 1.06A8.1 8.1 0 0 0 15.82 8a8.08 8.08 0 0 0-2.38-5.75Z" />
    </svg>
  );
}

function CalendarIcon({ className = 'h-4 w-4' }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" fill="currentColor" className={className} aria-hidden="true">
      <path d="M4 1.75a.75.75 0 0 1 1.5 0V3h5V1.75a.75.75 0 0 1 1.5 0V3A2 2 0 0 1 14 5v7a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2V1.75ZM4.5 6a1 1 0 0 0-1 1v4.5a1 1 0 0 0 1 1h7a1 1 0 0 0 1-1V7a1 1 0 0 0-1-1h-7Z" />
    </svg>
  );
}

function DraftIcon({ className = 'h-4 w-4' }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" fill="currentColor" className={className} aria-hidden="true">
      <path d="M4 2a1.5 1.5 0 0 0-1.5 1.5v9A1.5 1.5 0 0 0 4 14h8a1.5 1.5 0 0 0 1.5-1.5V6.621a1.5 1.5 0 0 0-.44-1.06L9.94 2.439A1.5 1.5 0 0 0 8.878 2H4Zm1 5.75A.75.75 0 0 1 5.75 7h4.5a.75.75 0 0 1 0 1.5h-4.5A.75.75 0 0 1 5 7.75Zm0 3A.75.75 0 0 1 5.75 10h4.5a.75.75 0 0 1 0 1.5h-4.5A.75.75 0 0 1 5 10.75Z" />
    </svg>
  );
}

function RecurringIcon({ className = 'h-4 w-4' }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" fill="currentColor" className={className} aria-hidden="true">
      <path d="M13.836 2.477a.75.75 0 0 1 .75.75v3.182a.75.75 0 0 1-.75.75h-3.182a.75.75 0 0 1 0-1.5h1.37l-.84-.841a4.5 4.5 0 0 0-7.08.681.75.75 0 0 1-1.3-.75 6 6 0 0 1 9.44-.908l.84.84V3.227a.75.75 0 0 1 .75-.75Zm-.911 7.5A.75.75 0 0 1 13.199 11a6 6 0 0 1-9.44.908l-.84-.84v1.68a.75.75 0 0 1-1.5 0V9.567a.75.75 0 0 1 .75-.75h3.182a.75.75 0 0 1 0 1.5H3.981l.841.841a4.5 4.5 0 0 0 7.08-.681.75.75 0 0 1 1.023-.274Z" />
    </svg>
  );
}

function TicketsIcon({ className = 'h-4 w-4' }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" fill="currentColor" className={className} aria-hidden="true">
      <path d="M2.5 3A1.5 1.5 0 0 0 1 4.5v2.086a.5.5 0 0 0 .293.455 1.75 1.75 0 0 1 0 3.918A.5.5 0 0 0 1 11.414V13.5A1.5 1.5 0 0 0 2.5 15h11a1.5 1.5 0 0 0 1.5-1.5v-2.086a.5.5 0 0 0-.293-.455 1.75 1.75 0 0 1 0-3.918A.5.5 0 0 0 15 6.586V4.5A1.5 1.5 0 0 0 13.5 3h-11Zm3.25 2.25a.75.75 0 0 1 .75.75v1a.75.75 0 0 1-1.5 0V6a.75.75 0 0 1 .75-.75Zm0 3.75a.75.75 0 0 1 .75.75v.25a.75.75 0 0 1-1.5 0v-.25a.75.75 0 0 1 .75-.75Zm4.5-3.75a.75.75 0 0 1 .75.75v4a.75.75 0 0 1-1.5 0V6a.75.75 0 0 1 .75-.75Z" />
    </svg>
  );
}

function SettingsIcon({ className = 'h-4 w-4' }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" fill="currentColor" className={className} aria-hidden="true">
      <path d="M6.955 1.45A.5.5 0 0 1 7.452 1h1.096a.5.5 0 0 1 .497.45l.17 1.699c.484.12.94.312 1.356.562l1.321-1.081a.5.5 0 0 1 .67.033l.774.775a.5.5 0 0 1 .034.67l-1.08 1.32c.25.417.44.873.561 1.357l1.699.17a.5.5 0 0 1 .45.497v1.096a.5.5 0 0 1-.45.497l-1.699.17c-.12.484-.312.94-.562 1.356l1.082 1.322a.5.5 0 0 1-.034.67l-.774.774a.5.5 0 0 1-.67.033l-1.322-1.08c-.416.25-.872.44-1.356.561l-.17 1.699a.5.5 0 0 1-.497.45H7.452a.5.5 0 0 1-.497-.45l-.17-1.699a4.973 4.973 0 0 1-1.356-.562L4.108 13.37a.5.5 0 0 1-.67-.033l-.774-.775a.5.5 0 0 1-.034-.67l1.08-1.32a4.971 4.971 0 0 1-.561-1.357l-1.699-.17A.5.5 0 0 1 1 8.548V7.452a.5.5 0 0 1 .45-.497l1.699-.17c.12-.484.312-.94.562-1.356L2.629 4.107a.5.5 0 0 1 .034-.67l.774-.774a.5.5 0 0 1 .67-.033L5.43 3.71a4.97 4.97 0 0 1 1.356-.561l.17-1.699ZM8 10a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z" />
    </svg>
  );
}

function HomeIcon({ className = 'h-4 w-4' }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" fill="currentColor" className={className} aria-hidden="true">
      <path d="M8.89 1.538a1.25 1.25 0 0 0-1.78 0L1.89 6.76A1.25 1.25 0 0 0 1.5 7.643V13a1.5 1.5 0 0 0 1.5 1.5h2.25A1.25 1.25 0 0 0 6.5 13.25v-2.5c0-.138.112-.25.25-.25h2.5c.138 0 .25.112.25.25v2.5A1.25 1.25 0 0 0 10.75 14.5H13A1.5 1.5 0 0 0 14.5 13V7.643a1.25 1.25 0 0 0-.39-.883L8.89 1.538Z" />
    </svg>
  );
}

function ChevronUpDownIcon({ className = 'h-4 w-4' }: { className?: string }) {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" className={className} aria-hidden="true">
      <path
        fillRule="evenodd"
        d="M10.53 3.47a.75.75 0 0 0-1.06 0L6.22 6.72a.75.75 0 0 0 1.06 1.06L10 5.06l2.72 2.72a.75.75 0 1 0 1.06-1.06l-3.25-3.25Zm-4.31 9.81 3.25 3.25a.75.75 0 0 0 1.06 0l3.25-3.25a.75.75 0 1 0-1.06-1.06L10 14.94l-2.72-2.72a.75.75 0 0 0-1.06 1.06Z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function CheckIcon({ className = 'h-4 w-4' }: { className?: string }) {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" className={className} aria-hidden="true">
      <path
        fillRule="evenodd"
        d="M16.704 4.153a.75.75 0 0 1 .143 1.052l-8 10.5a.75.75 0 0 1-1.127.075l-4.5-4.5a.75.75 0 1 1 1.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 0 1 1.05-.143Z"
        clipRule="evenodd"
      />
    </svg>
  );
}

export function DashboardShell({ user, onUserChange, onRefreshProfile }: DashboardShellProps) {
  const isMobile = useIsMobile();
  const navigate = useNavigate();
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [eventModuleEnabled, setEventModuleEnabled] = useState(true);
  const [guildInfo, setGuildInfo] = useState<GuildInfo | null>(null);
  const [availableGuilds, setAvailableGuilds] = useState<GuildSummary[]>([]);
  const [workspaceMenuOpen, setWorkspaceMenuOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [guildListLoading, setGuildListLoading] = useState(false);
  const [switchingGuildId, setSwitchingGuildId] = useState<string | null>(null);
  const workspaceMenuRef = useRef<HTMLDivElement>(null);
  const userMenuRef = useRef<HTMLDivElement>(null);

  useClickOutside([workspaceMenuRef, userMenuRef], () => {
    setWorkspaceMenuOpen(false);
    setUserMenuOpen(false);
  });

  const getUserRoleLevel = useCallback((): RoleLevel => {
    if (!user.active_guild_id) {
      return 'user';
    }

    const permission = user.authorized_guilds[user.active_guild_id];
    return permission?.role_level || 'user';
  }, [user]);

  const userHasPermission = useCallback(
    (required: RoleLevel): boolean => hasPermission(getUserRoleLevel(), required),
    [getUserRoleLevel],
  );

  const canViewMetrics = userHasPermission('discord_manager');
  const canViewEvents = eventModuleEnabled && userHasPermission('event_coordinator');
  const dashboardBasePath =
    user.active_guild_id && user.active_guild_id !== ALL_GUILDS_SENTINEL
      ? `/dashboard/${encodeURIComponent(user.active_guild_id)}`
      : '/';

  const dashboardPath = useCallback(
    (childPath: string = ''): string => {
      const normalizedChildPath = childPath.replace(/^\/+/, '');
      if (!normalizedChildPath) {
        return dashboardBasePath;
      }

      return `${dashboardBasePath}/${normalizedChildPath}`;
    },
    [dashboardBasePath],
  );

  useEffect(() => {
    let cancelled = false;

    const loadShellContext = async () => {
      const activeGuildId = user.active_guild_id;
      if (!activeGuildId || activeGuildId === '*') {
        if (!cancelled) {
          setEventModuleEnabled(false);
          setGuildInfo(null);
        }
        return;
      }

      try {
        const [guildConfigResponse, guildInfoResponse] = await Promise.all([
          guildApi.getGuildConfig(activeGuildId),
          guildApi.getGuildInfo(activeGuildId),
        ]);

        if (!cancelled) {
          setEventModuleEnabled(guildConfigResponse.data.events?.enabled !== false);
          setGuildInfo(guildInfoResponse.guild);
        }
      } catch {
        if (!cancelled) {
          setEventModuleEnabled(true);
          setGuildInfo(null);
        }
      }
    };

    void loadShellContext();

    return () => {
      cancelled = true;
    };
  }, [user.active_guild_id]);

  useEffect(() => {
    let cancelled = false;

    const loadAvailableGuilds = async () => {
      setGuildListLoading(true);

      try {
        const response = await authApi.getGuilds();

        if (!cancelled) {
          setAvailableGuilds(response.guilds);
        }
      } catch {
        if (!cancelled) {
          setAvailableGuilds([]);
        }
      } finally {
        if (!cancelled) {
          setGuildListLoading(false);
        }
      }
    };

    void loadAvailableGuilds();

    return () => {
      cancelled = true;
    };
  }, [user.active_guild_id, user.authorized_guilds, user.is_bot_owner]);

  useEffect(() => {
    if (!isMobile) {
      setSidebarOpen(false);
    }
  }, [isMobile]);

  useEffect(() => {
    setSidebarOpen(false);
    setWorkspaceMenuOpen(false);
    setUserMenuOpen(false);
  }, [location.pathname]);

  const sidebarSections: SidebarSection[] = useMemo(
    () => [
      {
        title: 'Overview',
        items: [
          {
            to: dashboardPath(),
            label: 'Dashboard',
            icon: <DashboardIcon />,
            visible: true,
          },
          {
            to: dashboardPath('metrics'),
            label: 'Metrics',
            icon: <MetricsIcon />,
            visible: canViewMetrics,
          },
        ],
      },
      {
        title: 'Operations',
        items: [
          { to: dashboardPath('users'), label: 'Users', icon: <UsersIcon />, visible: true },
          { to: dashboardPath('voice'), label: 'Voice', icon: <VoiceIcon />, visible: true },
          {
            to: dashboardPath('tickets'),
            label: 'Tickets',
            icon: <TicketsIcon />,
            visible: userHasPermission('discord_manager'),
          },
        ],
      },
      {
        title: 'Workspace',
        items: [
          {
            to: dashboardPath('events'),
            label: 'Events',
            icon: <CalendarIcon />,
            visible: canViewEvents,
          },
          {
            to: dashboardPath('events/drafts'),
            label: 'Drafts',
            icon: <DraftIcon />,
            visible: canViewEvents,
          },
          {
            to: dashboardPath('events/recurring'),
            label: 'Recurring',
            icon: <RecurringIcon />,
            visible: canViewEvents,
          },
        ],
      },
      {
        title: 'Account',
        items: [
          {
            to: dashboardPath('settings'),
            label: 'Settings',
            icon: <SettingsIcon />,
            visible: userHasPermission('bot_admin'),
          },
        ],
      },
    ],
    [canViewEvents, canViewMetrics, dashboardPath, userHasPermission],
  );

  const visibleSections = useMemo(
    () =>
      sidebarSections
        .map((section) => ({
          ...section,
          items: section.items.filter((item) => item.visible),
        }))
        .filter((section) => section.items.length > 0),
    [sidebarSections],
  );

  const allVisibleItems = useMemo(
    () => visibleSections.flatMap((section) => section.items),
    [visibleSections],
  );

  const activeItem = useMemo(() => {
    return (
      allVisibleItems.find((item) => {
        if (item.to === '/') {
          return location.pathname === '/';
        }

        return location.pathname === item.to || location.pathname.startsWith(`${item.to}/`);
      }) ?? allVisibleItems[0] ?? null
    );
  }, [allVisibleItems, location.pathname]);

  const handleSwitchWorkspace = async (guildId: string) => {
    if (guildId === user.active_guild_id) {
      setWorkspaceMenuOpen(false);
      return;
    }

    setSwitchingGuildId(guildId);

    try {
      await authApi.selectGuild(guildId);
      await onRefreshProfile();
      setWorkspaceMenuOpen(false);

      const requestedPrefix = `${dashboardBasePath}/`;
      const currentPath = location.pathname;
      const currentSuffix = currentPath.startsWith(requestedPrefix)
        ? currentPath.slice(requestedPrefix.length)
        : '';
      const nextPath = currentSuffix
        ? `/dashboard/${encodeURIComponent(guildId)}/${currentSuffix}`
        : `/dashboard/${encodeURIComponent(guildId)}`;

      navigate(`${nextPath}${location.search}`);
    } catch (err) {
      handleApiError(err, 'Failed to switch server');
    } finally {
      setSwitchingGuildId(null);
    }
  };

  const handleLogout = async () => {
    try {
      await authApi.logout();
      onUserChange(null);
      navigate('/');
      window.location.href = '/';
    } catch (err) {
      handleApiError(err, 'Failed to log out');
    }
  };

  const roleSubtext = (() => {
    if (user.is_bot_owner) {
      return 'Bot Owner';
    }

    if (user.active_guild_id && user.authorized_guilds?.[user.active_guild_id]) {
      const level = user.authorized_guilds[user.active_guild_id].role_level;
      return getRoleDisplayName(level);
    }

    if (user.is_admin) {
      return 'Admin';
    }

    if (user.is_moderator) {
      return 'Mod';
    }

    return null;
  })();

  const guildLabel =
    user.active_guild_id === ALL_GUILDS_SENTINEL
      ? 'All Guilds'
      : guildInfo?.guild_name || 'Active Workspace';
  const guildAvatar = guildInfo?.icon_url || null;
  const userAvatar = getDiscordAvatarUrl(user);

  const workspaceOptions = useMemo(() => {
    const options = [...availableGuilds];

    if (user.is_bot_owner) {
      options.unshift({
        guild_id: ALL_GUILDS_SENTINEL,
        guild_name: 'All Guilds',
        icon_url: null,
      });
    }

    return options;
  }, [availableGuilds, user.is_bot_owner]);

  const renderAvatar = (source: string | null, fallbackLabel: string, className: string) => {
    if (source) {
      return <img src={source} alt="" className={cn(className, 'object-cover')} />;
    }

    return (
      <div
        aria-hidden="true"
        className={cn(
          className,
            'flex items-center justify-center rounded-2xl bg-[#ffbb00]/15 text-xs font-bold uppercase tracking-[0.16em] text-[#ffcc4d]',
        )}
      >
        {getInitials(fallbackLabel)}
      </div>
    );
  };

  const sidebar = (
    <aside className="flex h-full flex-col border-r border-[#ffbb00]/15 bg-black/95 backdrop-blur-xl">
      <div className="border-b border-[#ffbb00]/15 p-4">
        <div className="flex items-center justify-between gap-3">
          <div className="relative min-w-0 flex-1" ref={workspaceMenuRef}>
            <button
              type="button"
              onClick={() => {
                setUserMenuOpen(false);
                setWorkspaceMenuOpen((open) => !open);
              }}
              className="group inline-flex w-full items-center gap-2 px-2.5 py-1.5 text-left font-bold tracking-wide text-[#f5deb3] transition hover:text-[#ffcc4d]"
              aria-haspopup="menu"
              aria-expanded={workspaceMenuOpen}
              aria-label="Switch workspace"
            >
              <span className="absolute inset-0 scale-50 rounded-lg bg-[#ffbb00]/8 opacity-0 transition ease-out group-hover:scale-100 group-hover:opacity-100 group-active:scale-105 group-active:bg-[#ffbb00]/14" />
              <span className="relative inline-flex min-w-0 flex-1 items-center justify-between gap-2">
                <span className="flex min-w-0 items-center gap-2">
                  {renderAvatar(guildAvatar, guildLabel, 'h-8 w-8 shrink-0 rounded-lg')}
                  <span className="truncate text-base font-semibold text-[#fff4cc]">{guildLabel}</span>
                </span>
                <span className="shrink-0 text-[#ffbb00]/70 transition group-hover:text-[#ffcc4d]">
                  <ChevronUpDownIcon className="h-5 w-5" />
                </span>
              </span>
            </button>

            {workspaceMenuOpen && (
              <div
                role="menu"
                aria-label="Workspace options"
                className="absolute left-0 right-0 z-20 mt-1 overflow-hidden rounded-2xl border border-[#ffbb00]/20 bg-black/95 shadow-2xl shadow-black/50 backdrop-blur-xl"
              >
                <div className="max-h-[24rem] space-y-1 overflow-y-auto p-2">
                  {workspaceOptions.length > 0 ? (
                    workspaceOptions.map((guild) => {
                      const isSelected = guild.guild_id === user.active_guild_id;
                      const isSwitching = switchingGuildId === guild.guild_id;

                      return (
                        <button
                          key={guild.guild_id}
                          type="button"
                          role="menuitemradio"
                          aria-checked={isSelected}
                          onClick={() => void handleSwitchWorkspace(guild.guild_id)}
                          disabled={switchingGuildId !== null}
                          className={cn(
                            'group flex w-full items-center justify-between gap-3 rounded-xl border border-transparent px-2.5 py-1.5 text-left text-sm font-medium transition',
                            isSelected
                              ? 'border-[#ffbb00]/25 bg-[#ffbb00]/12 text-[#ffdd73]'
                              : 'text-[#d6c7a3] hover:bg-[#ffbb00]/8 hover:text-[#fff1bf]',
                            switchingGuildId !== null && 'cursor-wait',
                          )}
                        >
                          <span className="flex min-w-0 items-center gap-3">
                            {renderAvatar(guild.icon_url, guild.guild_name, 'h-6 w-6 shrink-0 rounded-lg')}
                            <span className="truncate">{guild.guild_name}</span>
                          </span>
                          <span className="shrink-0 text-[#ffcc4d]">
                            {isSwitching ? (
                              <span className="text-xs font-semibold uppercase tracking-[0.16em] text-[#ffcc4d]/80">
                                Switching...
                              </span>
                            ) : isSelected ? (
                              <CheckIcon className="h-5 w-5" />
                            ) : null}
                          </span>
                        </button>
                      );
                    })
                  ) : (
                    <div className="rounded-xl border border-dashed border-[#ffbb00]/20 px-3 py-4 text-sm text-[#c9b789]">
                      {guildListLoading ? 'Loading workspaces...' : 'No workspaces available.'}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          {isMobile && (
            <button
              type="button"
              onClick={() => setSidebarOpen(false)}
              className="group relative inline-flex w-full max-w-fit items-center gap-2 rounded-lg p-2 text-sm leading-5 text-[#d6c7a3] transition hover:text-[#ffdd73]"
              aria-label="Close navigation"
            >
              <span className="absolute inset-0 scale-50 rounded-lg bg-[#ffbb00]/8 opacity-0 transition ease-out group-hover:scale-100 group-hover:opacity-100 group-active:scale-105 group-active:bg-[#ffbb00]/14" />
              <span className="relative">✕</span>
            </button>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4">
        <nav className="space-y-4" aria-label="Sidebar">
          {visibleSections.map((section) => (
            <div key={section.title}>
              <h3 className="px-3 text-[11px] font-semibold uppercase tracking-[0.24em] text-[#ffbb00]/55">
                {section.title}
              </h3>
              <div className="mt-1.5 space-y-1">
                {section.items.map((item) => {
                  const eventsRootPath = dashboardPath('events');
                  const isEventsChild =
                    item.to.startsWith(`${eventsRootPath}/`) && item.to !== eventsRootPath;

                  return (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      end={item.to === dashboardBasePath || item.to === eventsRootPath}
                      className={({ isActive }) =>
                        cn(
                          'group flex items-center gap-3 rounded-2xl px-3 py-2 text-sm font-medium transition',
                          isEventsChild && 'ml-4',
                          isActive
                            ? 'border border-[#ffbb00]/35 bg-[#ffbb00]/12 text-[#ffdd73] shadow-lg shadow-black/30'
                            : 'border border-transparent text-[#d6c7a3] hover:border-[#ffbb00]/15 hover:bg-[#ffbb00]/8 hover:text-[#fff1bf]',
                        )
                      }
                    >
                      {({ isActive }) => (
                        <>
                          <span
                            className={cn(
                              'flex h-4 w-4 items-center justify-center text-[#ffbb00]/55 transition',
                              isActive && 'text-[#ffcc4d]',
                            )}
                          >
                            {item.icon}
                          </span>
                          <span className="flex-1 py-0.5">{item.label}</span>
                          {item.badge ? (
                            <span className="rounded-full border border-[#ffbb00]/25 bg-[#ffbb00]/12 px-2 py-0.5 text-[11px] font-semibold text-[#ffdd73]">
                              {item.badge}
                            </span>
                          ) : null}
                        </>
                      )}
                    </NavLink>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>
      </div>

      <div className="border-t border-[#ffbb00]/15 p-4">
        <div className="relative w-full" ref={userMenuRef}>
          <button
            type="button"
            onClick={() => {
              setWorkspaceMenuOpen(false);
              setUserMenuOpen((open) => !open);
            }}
            className="group relative inline-flex w-full items-center justify-between gap-2 rounded-lg px-2.5 py-1.5 text-sm leading-5 text-[#d6c7a3] transition hover:text-[#fff1bf]"
            aria-haspopup="menu"
            aria-expanded={userMenuOpen}
            aria-label="Open user menu"
          >
            <span className="absolute inset-0 scale-50 rounded-lg bg-[#ffbb00]/8 opacity-0 transition ease-out group-hover:scale-100 group-hover:opacity-100 group-active:scale-105 group-active:bg-[#ffbb00]/14" />
            <span className="relative inline-flex items-center gap-2 min-w-0">
              <span className="relative inline-block flex-none">
                {renderAvatar(userAvatar, user.username, 'h-8 w-8 rounded-lg')}
              </span>
              <span className="flex min-w-0 grow flex-col text-left">
                <span className="truncate text-sm font-semibold text-[#fff4cc]">{user.username}</span>
                {roleSubtext ? (
                  <span className="truncate text-[11px] font-medium uppercase tracking-[0.18em] text-[#ffbb00]/60">
                    {roleSubtext}
                  </span>
                ) : null}
              </span>
            </span>
            <span className="relative inline-flex h-4 w-4 flex-none items-center justify-center text-[#ffbb00]/55">
              <svg viewBox="0 0 16 16" fill="currentColor" className="h-4 w-4" aria-hidden="true">
                <path d="M2 8a1.5 1.5 0 1 1 3 0 1.5 1.5 0 0 1-3 0ZM6.5 8a1.5 1.5 0 1 1 3 0 1.5 1.5 0 0 1-3 0ZM12.5 6.5a1.5 1.5 0 1 0 0 3 1.5 1.5 0 0 0 0-3Z" />
              </svg>
            </span>
          </button>

          {userMenuOpen && (
            <div
              role="menu"
              aria-label="User options"
              className="absolute inset-x-0 bottom-full z-20 mb-1 overflow-hidden rounded-2xl border border-[#ffbb00]/20 bg-black/95 shadow-2xl shadow-black/50 backdrop-blur-xl"
            >
              <div className="space-y-1 p-2">
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setUserMenuOpen(false);
                    navigate('/home');
                  }}
                  className="group flex w-full items-center gap-2.5 rounded-xl px-2.5 py-1.5 text-left text-sm font-medium text-[#f5deb3] transition hover:bg-[#ffbb00]/10 hover:text-[#fff1bf]"
                >
                  <HomeIcon className="h-4 w-4 flex-none text-[#ffbb00]/75" />
                  <span className="grow py-1">Public Home</span>
                </button>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => void handleLogout()}
                  className="group flex w-full items-center gap-2.5 rounded-xl px-2.5 py-1.5 text-left text-sm font-medium text-[#f5deb3] transition hover:bg-[#ffbb00]/10 hover:text-[#fff1bf]"
                >
                  <svg viewBox="0 0 16 16" fill="currentColor" className="h-4 w-4 flex-none text-[#ffbb00]/75" aria-hidden="true">
                    <path
                      fillRule="evenodd"
                      clipRule="evenodd"
                      d="M14 4.75A2.75 2.75 0 0 0 11.25 2h-3A2.75 2.75 0 0 0 5.5 4.75v.5a.75.75 0 0 0 1.5 0v-.5c0-.69.56-1.25 1.25-1.25h3c.69 0 1.25.56 1.25 1.25v6.5c0 .69-.56 1.25-1.25 1.25h-3c-.69 0-1.25-.56-1.25-1.25v-.5a.75.75 0 0 0-1.5 0v.5A2.75 2.75 0 0 0 8.25 14h3A2.75 2.75 0 0 0 14 11.25v-6.5Zm-9.47.47a.75.75 0 0 0-1.06 0L1.22 7.47a.75.75 0 0 0 0 1.06l2.25 2.25a.75.75 0 1 0 1.06-1.06l-.97-.97h7.19a.75.75 0 0 0 0-1.5H3.56l.97-.97a.75.75 0 0 0 0-1.06Z"
                    />
                  </svg>
                  <span className="grow py-1">Sign out</span>
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </aside>
  );

  return (
    <div className="dashboard-theme min-h-screen bg-black text-[#f5deb3]">
      <Toaster />

      <div className="flex min-h-screen">
        <div className="hidden w-72 shrink-0 lg:block">{sidebar}</div>

        {isMobile && sidebarOpen && (
          <>
            <div
              className="fixed inset-0 z-40 bg-slate-950/60 backdrop-blur-sm"
              onClick={() => setSidebarOpen(false)}
              aria-hidden="true"
            />
            <div className="fixed inset-y-0 left-0 z-50 w-72 max-w-[86vw] shadow-2xl shadow-black/50">
              {sidebar}
            </div>
          </>
        )}

        <div className="flex min-h-screen min-w-0 flex-1 flex-col">
          {isMobile && (
            <header className="sticky top-0 z-30 border-b border-[#ffbb00]/15 bg-black/90 backdrop-blur-xl">
              <div className="flex items-center gap-3 px-4 py-3 sm:px-6">
                <button
                  type="button"
                  onClick={() => setSidebarOpen(true)}
                  className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-[#ffbb00]/15 bg-[#120d00] text-[#f5deb3] transition hover:border-[#ffbb00]/35 hover:text-[#fff1bf]"
                  aria-label="Open navigation"
                >
                  ☰
                </button>
                <h1 className="dashboard-title truncate text-xl font-semibold text-[#fff4cc]">
                  {activeItem?.label || 'Workspace'}
                </h1>
              </div>
            </header>
          )}

          <main className="flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
            <div className="mx-auto w-full max-w-7xl">
              <Outlet />
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}
