import { useEffect, useMemo, useState } from 'react';
import { guildApi, GuildRole, DiscordChannel, GuildInfo, ReadOnlyYamlConfig } from '../api/endpoints';
import SearchableMultiSelect, { MultiSelectOption } from '../components/SearchableMultiSelect';
import SearchableSelect, { SelectOption } from '../components/SearchableSelect';
import AccordionSection from '../components/AccordionSection';

interface DashboardBotSettingsProps {
  guildId: string;
}

const DashboardBotSettings = ({ guildId }: DashboardBotSettingsProps) => {
  const [roles, setRoles] = useState<GuildRole[]>([]);
  const [channels, setChannels] = useState<DiscordChannel[]>([]);
  // Use strings for role IDs to preserve 64-bit Discord snowflake precision
  const [botAdmins, setBotAdmins] = useState<string[]>([]);
  const [discordManagers, setDiscordManagers] = useState<string[]>([]);
  const [moderators, setModerators] = useState<string[]>([]);
  const [staff, setStaff] = useState<string[]>([]);
  const [botVerifiedRole, setBotVerifiedRole] = useState<string[]>([]);
  const [mainRole, setMainRole] = useState<string[]>([]);
  const [affiliateRole, setAffiliateRole] = useState<string[]>([]);
  const [nonmemberRole, setNonmemberRole] = useState<string[]>([]);
  const [voiceSelectableRoles, setVoiceSelectableRoles] = useState<string[]>([]);
  const [verificationChannelId, setVerificationChannelId] = useState<string | null>(null);
  const [botSpamChannelId, setBotSpamChannelId] = useState<string | null>(null);
  const [publicAnnouncementChannelId, setPublicAnnouncementChannelId] = useState<string | null>(null);
  const [leadershipAnnouncementChannelId, setLeadershipAnnouncementChannelId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [voiceSaving, setVoiceSaving] = useState(false);
  const [channelSaving, setChannelSaving] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [voiceStatusMessage, setVoiceStatusMessage] = useState<string | null>(null);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [channelStatusMessage, setChannelStatusMessage] = useState<string | null>(null);
  const [channelError, setChannelError] = useState<string | null>(null);
  
  // Organization settings
  const [organizationSid, setOrganizationSid] = useState<string>('');
  const [organizationName, setOrganizationName] = useState<string>('');
  const [orgSidInput, setOrgSidInput] = useState<string>('');
  const [orgValidating, setOrgValidating] = useState(false);
  const [orgSaving, setOrgSaving] = useState(false);
  const [orgStatusMessage, setOrgStatusMessage] = useState<string | null>(null);
  const [orgError, setOrgError] = useState<string | null>(null);

  // Guild header and read-only YAML snapshot
  const [guildInfo, setGuildInfo] = useState<GuildInfo | null>(null);
  const [readOnly, setReadOnly] = useState<ReadOnlyYamlConfig | null>(null);

  const roleOptions: MultiSelectOption[] = useMemo(
    () => roles.map((role) => ({ id: role.id, name: role.name })),
    [roles]
  );

  const channelOptions: SelectOption[] = useMemo(
    () =>
      channels.map((channel) => ({
        id: channel.id,
        name: channel.name,
        category: channel.category ?? undefined,
      })),
    [channels]
  );

  useEffect(() => {
    const loadData = async () => {
      if (!guildId) {
        return;
      }
      setLoading(true);
      setStatusMessage(null);
      setError(null);

      try {
        const [infoResponse, configResponse, rolesResponse, settingsResponse, voiceSelectableResponse, channelsResponse, channelSettingsResponse, orgSettingsResponse] = await Promise.all([
          guildApi.getGuildInfo(guildId),
          guildApi.getGuildConfig(guildId),
          guildApi.getDiscordRoles(guildId),
          guildApi.getBotRoleSettings(guildId),
          guildApi.getVoiceSelectableRoles(guildId),
          guildApi.getDiscordChannels(guildId),
          guildApi.getBotChannelSettings(guildId),
          guildApi.getOrganizationSettings(guildId),
        ]);

        setGuildInfo(infoResponse.guild);
        setReadOnly(configResponse.data.read_only ?? null);
        setRoles(rolesResponse.roles);
        setChannels(channelsResponse.channels);
        setBotAdmins(settingsResponse.bot_admins);
        setDiscordManagers(settingsResponse.discord_managers || []);
        setModerators(settingsResponse.moderators || []);
        setStaff(settingsResponse.staff || []);
        setBotVerifiedRole(settingsResponse.bot_verified_role || []);
        setMainRole(settingsResponse.main_role || []);
        setAffiliateRole(settingsResponse.affiliate_role || []);
        setNonmemberRole(settingsResponse.nonmember_role || []);
        setVoiceSelectableRoles(voiceSelectableResponse.selectable_roles || []);
        setVerificationChannelId(channelSettingsResponse.verification_channel_id);
        setBotSpamChannelId(channelSettingsResponse.bot_spam_channel_id);
        setPublicAnnouncementChannelId(channelSettingsResponse.public_announcement_channel_id);
        setLeadershipAnnouncementChannelId(channelSettingsResponse.leadership_announcement_channel_id);
        setOrganizationSid(orgSettingsResponse.organization_sid || '');
        setOrganizationName(orgSettingsResponse.organization_name || '');
        setOrgSidInput(orgSettingsResponse.organization_sid || '');
      } catch (err) {
        console.error(err);
        setError('Failed to load bot settings.');
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, [guildId]);

  const handleSave = async () => {
    setSaving(true);
    setStatusMessage(null);
    setError(null);

    try {
      const patch = {
        roles: {
          bot_admins: botAdmins,
          discord_managers: discordManagers,
          moderators: moderators,
          staff: staff,
          bot_verified_role: botVerifiedRole,
          main_role: mainRole,
          affiliate_role: affiliateRole,
          nonmember_role: nonmemberRole,
        },
      };
      const response = await guildApi.patchGuildConfig(guildId, patch);
      const updated = response.data.roles;
      setBotAdmins(updated.bot_admins);
      setDiscordManagers(updated.discord_managers || []);
      setModerators(updated.moderators || []);
      setStaff(updated.staff || []);
      setBotVerifiedRole(updated.bot_verified_role || []);
      setMainRole(updated.main_role || []);
      setMainRole(updated.main_role || []);
      setAffiliateRole(updated.affiliate_role || []);
      setNonmemberRole(updated.nonmember_role || []);
      setStatusMessage('Settings saved successfully.');
    } catch (err) {
      console.error(err);
      setError('Failed to save settings.');
    } finally {
      setSaving(false);
    }
  };

  const handleVoiceRolesSave = async () => {
    setVoiceSaving(true);
    setVoiceStatusMessage(null);
    setVoiceError(null);

    try {
      const response = await guildApi.patchGuildConfig(guildId, {
        voice: { selectable_roles: voiceSelectableRoles },
      });
      const updated = response.data.voice;
      setVoiceSelectableRoles(updated.selectable_roles || []);
      setVoiceStatusMessage('Selectable roles updated successfully.');
    } catch (err) {
      console.error(err);
      setVoiceError('Failed to save selectable roles.');
    } finally {
      setVoiceSaving(false);
    }
  };

  const handleChannelsSave = async () => {
    setChannelSaving(true);
    setChannelStatusMessage(null);
    setChannelError(null);

    try {
      const response = await guildApi.patchGuildConfig(guildId, {
        channels: {
          verification_channel_id: verificationChannelId,
          bot_spam_channel_id: botSpamChannelId,
          public_announcement_channel_id: publicAnnouncementChannelId,
          leadership_announcement_channel_id: leadershipAnnouncementChannelId,
        },
      });
      const updated = response.data.channels;
      setVerificationChannelId(updated.verification_channel_id);
      setBotSpamChannelId(updated.bot_spam_channel_id);
      setPublicAnnouncementChannelId(updated.public_announcement_channel_id);
      setLeadershipAnnouncementChannelId(updated.leadership_announcement_channel_id);
      setChannelStatusMessage('Channel settings saved successfully.');
    } catch (err) {
      console.error(err);
      setChannelError('Failed to save channel settings.');
    } finally {
      setChannelSaving(false);
    }
  };

  const handleOrgValidate = async () => {
    if (!orgSidInput.trim()) {
      setOrgError('Please enter an organization SID');
      return;
    }

    setOrgValidating(true);
    setOrgError(null);
    setOrgStatusMessage(null);

    try {
      const result = await guildApi.validateOrganizationSid(guildId, orgSidInput.trim());
      
      if (result.is_valid && result.name) {
        setOrganizationName(result.name);
        setOrgStatusMessage(`✓ Valid organization: ${result.name} (${result.sid})`);
      } else {
        setOrgError(result.error || 'Organization not found');
        setOrganizationName('');
      }
    } catch (err) {
      console.error(err);
      setOrgError('Failed to validate organization SID. Please try again.');
    } finally {
      setOrgValidating(false);
    }
  };

  const handleOrgSave = async () => {
    if (!organizationName) {
      setOrgError('Please validate the organization SID first');
      return;
    }

    setOrgSaving(true);
    setOrgError(null);
    setOrgStatusMessage(null);

    try {
      const response = await guildApi.patchGuildConfig(guildId, {
        organization: {
          organization_sid: orgSidInput.trim().toUpperCase() || null,
          organization_name: organizationName || null,
        },
      });
      const updated = response.data.organization;
      setOrganizationSid(updated.organization_sid || '');
      setOrganizationName(updated.organization_name || '');
      setOrgSidInput(updated.organization_sid || '');
      setOrgStatusMessage('Organization settings saved successfully!');
    } catch (err) {
      console.error(err);
      setOrgError('Failed to save organization settings.');
    } finally {
      setOrgSaving(false);
    }
  };

  if (loading) {
    return <div className="text-gray-400">Loading bot settings...</div>;
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        {guildInfo?.icon_url && (
          <img
            src={guildInfo.icon_url}
            alt={guildInfo.guild_name}
            className="h-12 w-12 rounded-full border border-slate-600"
          />
        )}
        <div>
          <h2 className="text-3xl font-bold text-white">
            {guildInfo ? guildInfo.guild_name : 'Server Configuration'}
          </h2>
          <p className="mt-1 text-gray-400">
            Configure roles, channels, voice, and organization settings.
          </p>
        </div>
      </div>
      {/* Read-only YAML snapshot */}
      {readOnly && (
        <AccordionSection title="🛡️ Global YAML (Read-Only)" level={1}>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <div className="rounded-lg border border-slate-700 bg-slate-800/60 p-4">
              <h5 className="text-sm font-semibold text-white mb-2">RSI Config</h5>
              <pre className="text-xs text-gray-300 whitespace-pre-wrap break-words">
                {JSON.stringify(readOnly.rsi ?? {}, null, 2)}
              </pre>
            </div>
            <div className="rounded-lg border border-slate-700 bg-slate-800/60 p-4">
              <h5 className="text-sm font-semibold text-white mb-2">Voice (Global)</h5>
              <pre className="text-xs text-gray-300 whitespace-pre-wrap break-words mb-2">
                {JSON.stringify(readOnly.voice ?? {}, null, 2)}
              </pre>
              <div className="text-xs text-gray-200">
                <span className="font-semibold">voice_debug_logging_enabled:</span>{' '}
                <span>{String(readOnly.voice_debug_logging_enabled ?? false)}</span>
              </div>
            </div>
          </div>
        </AccordionSection>
      )}

      {/* Status Messages */}
      {error && (
        <div className="rounded-lg border border-red-700 bg-red-900/30 p-4 text-red-200">
          {error}
        </div>
      )}
      {statusMessage && (
        <div className="rounded-lg border border-green-700 bg-green-900/20 p-4 text-green-200">
          {statusMessage}
        </div>
      )}
      {voiceError && (
        <div className="rounded-lg border border-red-700 bg-red-900/30 p-4 text-red-200">
          {voiceError}
        </div>
      )}
      {voiceStatusMessage && (
        <div className="rounded-lg border border-green-700 bg-green-900/20 p-4 text-green-200">
          {voiceStatusMessage}
        </div>
      )}
      {channelError && (
        <div className="rounded-lg border border-red-700 bg-red-900/30 p-4 text-red-200">
          {channelError}
        </div>
      )}
      {channelStatusMessage && (
        <div className="rounded-lg border border-green-700 bg-green-900/20 p-4 text-green-200">
          {channelStatusMessage}
        </div>
      )}
      {orgError && (
        <div className="rounded-lg border border-red-700 bg-red-900/30 p-4 text-red-200">
          {orgError}
        </div>
      )}
      {orgStatusMessage && (
        <div className="rounded-lg border border-green-700 bg-green-900/20 p-4 text-green-200">
          {orgStatusMessage}
        </div>
      )}

      {/* Organization Settings - Top Level Accordion */}
      <AccordionSection title="🏢 Organization Verification" level={1}>
        <div className="space-y-4">
          <p className="text-sm text-gray-300">
            Configure the Star Citizen organization for member verification. Enter your organization's SID (Spectrum ID) to validate members.
          </p>
          
          <div>
            <h5 className="text-sm font-semibold text-white mb-1">Organization SID</h5>
            <p className="text-xs text-gray-400 mb-2">
              Enter your organization's Spectrum ID (e.g., "TEST"). This is used to verify member status.
            </p>
            <div className="flex gap-2">
              <input
                type="text"
                value={orgSidInput}
                onChange={(e) => setOrgSidInput(e.target.value.toUpperCase())}
                placeholder="Enter SID (e.g., TEST)"
                className="flex-1 rounded-md border border-slate-600 bg-slate-800 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                maxLength={20}
              />
              <button
                onClick={handleOrgValidate}
                disabled={orgValidating || !orgSidInput.trim()}
                className="rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow transition hover:bg-blue-500 disabled:cursor-not-allowed disabled:bg-slate-600 disabled:opacity-60"
              >
                {orgValidating ? 'Validating...' : 'Validate'}
              </button>
            </div>
          </div>

          {organizationName && (
            <div className="rounded-lg border border-green-700 bg-green-900/20 p-4">
              <h5 className="text-sm font-semibold text-green-200 mb-1">Organization Found</h5>
              <p className="text-sm text-green-100">{organizationName}</p>
              <p className="text-xs text-green-300 mt-1">SID: {orgSidInput || organizationSid}</p>
            </div>
          )}

          <div className="flex justify-end pt-2">
            <button
              onClick={handleOrgSave}
              disabled={orgSaving || !organizationName}
              className="rounded-md bg-emerald-600 px-5 py-2 text-sm font-semibold text-white shadow transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:bg-slate-600 disabled:opacity-60"
            >
              {orgSaving ? 'Saving...' : 'Save Organization Settings'}
            </button>
          </div>
        </div>
      </AccordionSection>

      {/* Assignable Roles - Top Level Accordion */}
      <AccordionSection title="📁 Assignable Roles" level={1}>
        <div className="space-y-4">
          {/* Bot Administration - Second Level Accordion */}
          <AccordionSection title="📁 Bot Administration" level={2}>
            <div className="space-y-4">
              <div className="rounded-lg border border-indigo-700 bg-indigo-900/20 p-3 mb-4">
                <h5 className="text-sm font-semibold text-indigo-200 mb-1">Permission Hierarchy</h5>
                <p className="text-xs text-indigo-100">
                  Permissions are inherited from higher levels. Bot Admins have all permissions, 
                  Discord Managers can manage users, Moderators handle moderation, and Staff have basic access.
                </p>
                <div className="mt-2 text-xs text-indigo-200 font-mono">
                  Bot Owner &gt; Bot Admin &gt; Discord Manager &gt; Moderator &gt; Staff &gt; User
                </div>
              </div>

              <div>
                <h5 className="text-sm font-semibold text-white mb-1">Bot Admin Roles</h5>
                <p className="text-xs text-gray-400 mb-2">
                  Full bot administration access. Can configure all settings, manage all roles, and access all commands.
                </p>
                <SearchableMultiSelect
                  options={roleOptions}
                  selected={botAdmins}
                  onChange={setBotAdmins}
                  placeholder="Search and select admin roles"
                  componentId="bot-admins"
                />
              </div>

              <div>
                <h5 className="text-sm font-semibold text-white mb-1">Discord Manager Roles</h5>
                <p className="text-xs text-gray-400 mb-2">
                  Elevated permissions for user management. Can search/manage users and view member data.
                </p>
                <SearchableMultiSelect
                  options={roleOptions}
                  selected={discordManagers}
                  onChange={setDiscordManagers}
                  placeholder="Search and select Discord manager roles"
                  componentId="discord-managers"
                />
              </div>

              <div>
                <h5 className="text-sm font-semibold text-white mb-1">Moderator Roles</h5>
                <p className="text-xs text-gray-400 mb-2">
                  Moderation permissions. Can manage voice channels, reset verification timers, and run bulk checks.
                </p>
                <SearchableMultiSelect
                  options={roleOptions}
                  selected={moderators}
                  onChange={setModerators}
                  placeholder="Search and select moderator roles"
                  componentId="moderators"
                />
              </div>

              <div>
                <h5 className="text-sm font-semibold text-white mb-1">Staff Roles</h5>
                <p className="text-xs text-gray-400 mb-2">
                  Basic staff access. Can view dashboard and access read-only features.
                </p>
                <SearchableMultiSelect
                  options={roleOptions}
                  selected={staff}
                  onChange={setStaff}
                  placeholder="Search and select staff roles"
                  componentId="staff"
                />
              </div>
            </div>
          </AccordionSection>

          {/* Verification Roles - Second Level Accordion */}
          <AccordionSection title="✅ Verification Roles" level={2}>
            <div className="space-y-4">
              <div>
                <h5 className="text-sm font-semibold text-white mb-1">Base Verified Role</h5>
                <p className="text-xs text-gray-400 mb-2">
                  Role assigned to ALL users who complete RSI verification, regardless of organization membership status.
                </p>
                <SearchableMultiSelect
                  options={roleOptions}
                  selected={botVerifiedRole}
                  onChange={setBotVerifiedRole}
                  placeholder="Search and select base verified role"
                  componentId="bot-verified-role"
                />
              </div>
            </div>
          </AccordionSection>

          {/* Member Categories - Second Level Accordion */}
          <AccordionSection title="📁 Member Categories" level={2}>
            <div className="space-y-4">
              <div>
                <h5 className="text-sm font-semibold text-white mb-1">Main Member Role</h5>
                <p className="text-xs text-gray-400 mb-2">
                  Primary organization members with full access.
                </p>
                <SearchableMultiSelect
                  options={roleOptions}
                  selected={mainRole}
                  onChange={setMainRole}
                  placeholder="Search and select main member role"
                  componentId="main-role"
                />
              </div>

              <div>
                <h5 className="text-sm font-semibold text-white mb-1">Affiliate Member Role</h5>
                <p className="text-xs text-gray-400 mb-2">
                  Affiliate organization members with limited access.
                </p>
                <SearchableMultiSelect
                  options={roleOptions}
                  selected={affiliateRole}
                  onChange={setAffiliateRole}
                  placeholder="Search and select affiliate role"
                  componentId="affiliate-role"
                />
              </div>

              <div>
                <h5 className="text-sm font-semibold text-white mb-1">Non-Member Role</h5>
                <p className="text-xs text-gray-400 mb-2">
                  Non-organization members or guests with basic access.
                </p>
                <SearchableMultiSelect
                  options={roleOptions}
                  selected={nonmemberRole}
                  onChange={setNonmemberRole}
                  placeholder="Search and select non-member role"
                  componentId="nonmember-role"
                />
              </div>
            </div>
          </AccordionSection>

          {/* Voice Bot Configuration */}
          <AccordionSection title="📁 Voice Bot Configuration" level={2}>
            <div className="space-y-4">
              <div>
                <h5 className="text-sm font-semibold text-white mb-1">Selectable Voice Roles</h5>
                <p className="text-xs text-gray-400 mb-2">
                  Only these roles will appear when members configure voice channel features.
                </p>
                <SearchableMultiSelect
                  options={roleOptions}
                  selected={voiceSelectableRoles}
                  onChange={setVoiceSelectableRoles}
                  placeholder="Choose roles exposed to the voice bot"
                />
              </div>

              <div className="flex justify-end">
                <button
                  onClick={handleVoiceRolesSave}
                  disabled={voiceSaving}
                  className="rounded-md bg-emerald-600 px-5 py-2 text-sm font-semibold text-white shadow transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:bg-slate-600 disabled:opacity-60"
                >
                  {voiceSaving ? 'Saving...' : 'Save Voice Roles'}
                </button>
              </div>
            </div>
          </AccordionSection>
        </div>
      </AccordionSection>

      {/* Channel Configuration - Top Level Accordion */}
      <AccordionSection title="📺 Channel Configuration" level={1}>
        <div className="space-y-4">
          <div>
            <h5 className="text-sm font-semibold text-white mb-1">Verification Channel</h5>
            <p className="text-xs text-gray-400 mb-2">
              Channel where verification messages and notifications are sent.
            </p>
            <SearchableSelect
              options={channelOptions}
              selected={verificationChannelId}
              onChange={setVerificationChannelId}
              placeholder="Search and select verification channel"
            />
          </div>

          <div>
            <h5 className="text-sm font-semibold text-white mb-1">Bot Spam Channel</h5>
            <p className="text-xs text-gray-400 mb-2">
              Channel for bot commands and testing.
            </p>
            <SearchableSelect
              options={channelOptions}
              selected={botSpamChannelId}
              onChange={setBotSpamChannelId}
              placeholder="Search and select bot spam channel"
            />
          </div>

          <div>
            <h5 className="text-sm font-semibold text-white mb-1">Public Announcement Channel</h5>
            <p className="text-xs text-gray-400 mb-2">
              Channel for public announcements to all members.
            </p>
            <SearchableSelect
              options={channelOptions}
              selected={publicAnnouncementChannelId}
              onChange={setPublicAnnouncementChannelId}
              placeholder="Search and select announcement channel"
            />
          </div>

          <div>
            <h5 className="text-sm font-semibold text-white mb-1">Leadership Announcement Channel</h5>
            <p className="text-xs text-gray-400 mb-2">
              Channel for leadership-specific announcements.
            </p>
            <SearchableSelect
              options={channelOptions}
              selected={leadershipAnnouncementChannelId}
              onChange={setLeadershipAnnouncementChannelId}
              placeholder="Search and select leadership channel"
            />
          </div>

          <div className="flex justify-end">
            <button
              onClick={handleChannelsSave}
              disabled={channelSaving}
              className="rounded-md bg-emerald-600 px-5 py-2 text-sm font-semibold text-white shadow transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:bg-slate-600 disabled:opacity-60"
            >
              {channelSaving ? 'Saving...' : 'Save Channel Settings'}
            </button>
          </div>
        </div>
      </AccordionSection>

      {/* Save Button */}
      <div className="flex justify-end pt-4 border-t border-slate-700">
        <button
          onClick={handleSave}
          disabled={saving}
          className="rounded-lg bg-indigo-600 px-8 py-3 font-semibold text-white shadow-lg transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:bg-slate-600 disabled:opacity-50"
        >
          {saving ? 'Saving Changes...' : 'Save Configuration'}
        </button>
      </div>
    </div>
  );
};

export default DashboardBotSettings;
