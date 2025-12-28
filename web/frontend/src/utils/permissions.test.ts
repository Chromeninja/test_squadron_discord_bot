import { describe, expect, it } from 'vitest';
import {
  hasPermission,
  getRoleDisplayName,
  getRoleBadgeColor,
  getRolesAtOrAbove,
  ROLE_HIERARCHY,
  type RoleLevel,
} from './permissions';

describe('Permission Utilities', () => {
  describe('hasPermission', () => {
    it('returns true when user role equals required role', () => {
      expect(hasPermission('bot_admin', 'bot_admin')).toBe(true);
      expect(hasPermission('moderator', 'moderator')).toBe(true);
      expect(hasPermission('staff', 'staff')).toBe(true);
    });

    it('returns true when user role exceeds required role', () => {
      expect(hasPermission('bot_owner', 'bot_admin')).toBe(true);
      expect(hasPermission('bot_admin', 'moderator')).toBe(true);
      expect(hasPermission('moderator', 'staff')).toBe(true);
      expect(hasPermission('staff', 'user')).toBe(true);
    });

    it('returns false when user role is below required role', () => {
      expect(hasPermission('user', 'staff')).toBe(false);
      expect(hasPermission('staff', 'moderator')).toBe(false);
      expect(hasPermission('moderator', 'bot_admin')).toBe(false);
      expect(hasPermission('bot_admin', 'bot_owner')).toBe(false);
    });

    it('bot_owner has access to everything', () => {
      const roles: RoleLevel[] = ['bot_owner', 'bot_admin', 'discord_manager', 'moderator', 'staff', 'user'];
      for (const required of roles) {
        expect(hasPermission('bot_owner', required)).toBe(true);
      }
    });

    it('user only has access to user level', () => {
      expect(hasPermission('user', 'user')).toBe(true);
      expect(hasPermission('user', 'staff')).toBe(false);
      expect(hasPermission('user', 'moderator')).toBe(false);
      expect(hasPermission('user', 'bot_admin')).toBe(false);
    });
  });

  describe('getRoleDisplayName', () => {
    it('returns correct display name for each role', () => {
      expect(getRoleDisplayName('bot_owner')).toBe('Bot Owner');
      expect(getRoleDisplayName('bot_admin')).toBe('Bot Admin');
      expect(getRoleDisplayName('discord_manager')).toBe('Discord Manager');
      expect(getRoleDisplayName('moderator')).toBe('Moderator');
      expect(getRoleDisplayName('staff')).toBe('Staff');
      expect(getRoleDisplayName('user')).toBe('User');
    });
  });

  describe('getRoleBadgeColor', () => {
    it('returns valid color classes for each role', () => {
      const roles: RoleLevel[] = ['bot_owner', 'bot_admin', 'discord_manager', 'moderator', 'staff', 'user'];
      for (const role of roles) {
        const color = getRoleBadgeColor(role);
        expect(color).toBeTruthy();
        expect(color).toContain('bg-');
        expect(color).toContain('text-');
      }
    });

    it('returns distinct colors for different privilege levels', () => {
      const ownerColor = getRoleBadgeColor('bot_owner');
      const adminColor = getRoleBadgeColor('bot_admin');
      const userColor = getRoleBadgeColor('user');

      expect(ownerColor).not.toBe(adminColor);
      expect(adminColor).not.toBe(userColor);
    });
  });

  describe('getRolesAtOrAbove', () => {
    it('returns all roles for user level', () => {
      const roles = getRolesAtOrAbove('user');
      expect(roles).toContain('user');
      expect(roles).toContain('staff');
      expect(roles).toContain('moderator');
      expect(roles).toContain('bot_admin');
      expect(roles).toContain('bot_owner');
      expect(roles.length).toBe(6);
    });

    it('returns only highest roles for bot_owner level', () => {
      const roles = getRolesAtOrAbove('bot_owner');
      expect(roles).toEqual(['bot_owner']);
    });

    it('returns moderator and above for moderator level', () => {
      const roles = getRolesAtOrAbove('moderator');
      expect(roles).toContain('moderator');
      expect(roles).toContain('discord_manager');
      expect(roles).toContain('bot_admin');
      expect(roles).toContain('bot_owner');
      expect(roles).not.toContain('staff');
      expect(roles).not.toContain('user');
    });

    it('returns roles in descending privilege order', () => {
      const roles = getRolesAtOrAbove('user');
      for (let i = 0; i < roles.length - 1; i++) {
        expect(ROLE_HIERARCHY[roles[i]]).toBeGreaterThan(ROLE_HIERARCHY[roles[i + 1]]);
      }
    });
  });

  describe('ROLE_HIERARCHY', () => {
    it('has correct relative ordering', () => {
      expect(ROLE_HIERARCHY.bot_owner).toBeGreaterThan(ROLE_HIERARCHY.bot_admin);
      expect(ROLE_HIERARCHY.bot_admin).toBeGreaterThan(ROLE_HIERARCHY.discord_manager);
      expect(ROLE_HIERARCHY.discord_manager).toBeGreaterThan(ROLE_HIERARCHY.moderator);
      expect(ROLE_HIERARCHY.moderator).toBeGreaterThan(ROLE_HIERARCHY.staff);
      expect(ROLE_HIERARCHY.staff).toBeGreaterThan(ROLE_HIERARCHY.user);
    });

    it('user is the lowest level (value 1)', () => {
      expect(ROLE_HIERARCHY.user).toBe(1);
    });

    it('bot_owner is the highest level (value 6)', () => {
      expect(ROLE_HIERARCHY.bot_owner).toBe(6);
    });
  });
});
