/**
 * Permission hierarchy utilities for frontend role-based access control.
 * 
 * Matches backend permission levels from core/dependencies.py
 */

export type RoleLevel = 'bot_owner' | 'bot_admin' | 'discord_manager' | 'moderator' | 'staff' | 'user';

/**
 * Role hierarchy values (higher = more privilege).
 * Must match backend ROLE_HIERARCHY in core/dependencies.py.
 */
export const ROLE_HIERARCHY: Record<RoleLevel, number> = {
  bot_owner: 6,
  bot_admin: 5,
  discord_manager: 4,
  moderator: 3,
  staff: 2,
  user: 1,
};

/**
 * Check if a user's role meets the minimum required level.
 * 
 * @param userRole - The user's current role level
 * @param requiredRole - The minimum required role level
 * @returns true if user has sufficient permissions
 * 
 * @example
 * hasPermission('bot_admin', 'moderator') // true (bot_admin > moderator)
 * hasPermission('staff', 'moderator') // false (staff < moderator)
 */
export function hasPermission(userRole: RoleLevel, requiredRole: RoleLevel): boolean {
  const userLevel = ROLE_HIERARCHY[userRole] || 0;
  const requiredLevel = ROLE_HIERARCHY[requiredRole] || 0;
  return userLevel >= requiredLevel;
}

/**
 * Get a user-friendly display name for a role level.
 */
export function getRoleDisplayName(role: RoleLevel): string {
  const displayNames: Record<RoleLevel, string> = {
    bot_owner: 'Bot Owner',
    bot_admin: 'Bot Admin',
    discord_manager: 'Discord Manager',
    moderator: 'Moderator',
    staff: 'Staff',
    user: 'User',
  };
  return displayNames[role] || 'Unknown';
}

/**
 * Get badge color classes for a role level.
 */
export function getRoleBadgeColor(role: RoleLevel): string {
  const colors: Record<RoleLevel, string> = {
    bot_owner: 'bg-purple-900 text-purple-200',
    bot_admin: 'bg-red-900 text-red-200',
    discord_manager: 'bg-orange-900 text-orange-200',
    moderator: 'bg-blue-900 text-blue-200',
    staff: 'bg-green-900 text-green-200',
    user: 'bg-gray-700 text-gray-300',
  };
  return colors[role] || 'bg-gray-700 text-gray-300';
}

/**
 * Get all roles at or above a certain level (for UI filtering).
 */
export function getRolesAtOrAbove(minRole: RoleLevel): RoleLevel[] {
  const minLevel = ROLE_HIERARCHY[minRole];
  return (Object.keys(ROLE_HIERARCHY) as RoleLevel[])
    .filter(role => ROLE_HIERARCHY[role] >= minLevel)
    .sort((a, b) => ROLE_HIERARCHY[b] - ROLE_HIERARCHY[a]); // Descending order
}
