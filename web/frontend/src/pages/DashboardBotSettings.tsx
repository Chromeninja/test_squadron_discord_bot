import { useEffect, useMemo, useState } from 'react';
import { guildApi, GuildRole, DiscordChannel, GuildInfo, ReadOnlyYamlConfig, RoleDelegationPolicyPayload } from '../api/endpoints';
import SearchableMultiSelect, { MultiSelectOption } from '../components/SearchableMultiSelect';
import SearchableSelect, { SelectOption } from '../components/SearchableSelect';
import AccordionSection from '../components/AccordionSection';
import { handleApiError } from '../utils/toast';
import { Alert, Button, Card, CardBody, Input } from '../components/ui';

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
  const [delegationPolicies, setDelegationPolicies] = useState<RoleDelegationPolicyPayload[]>([]);
  const [voiceSelectableRoles, setVoiceSelectableRoles] = useState<string[]>([]);
  const [verificationChannelId, setVerificationChannelId] = useState<string | null>(null);
  const [botSpamChannelId, setBotSpamChannelId] = useState<string | null>(null);
  const [publicAnnouncementChannelId, setPublicAnnouncementChannelId] = useState<string | null>(null);
  const [leadershipAnnouncementChannelId, setLeadershipAnnouncementChannelId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  
  // Organization settings
  const [organizationSid, setOrganizationSid] = useState<string>('');
  const [organizationName, setOrganizationName] = useState<string>('');
  const [orgSidInput, setOrgSidInput] = useState<string>('');
  const [orgValidating, setOrgValidating] = useState(false);
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

  const addDelegationPolicy = () =>
    setDelegationPolicies((prev) => [
      ...prev,
      {
        grantor_role_ids: [],
        target_role_id: '',
        prerequisite_role_ids_all: [],
        prerequisite_role_ids_any: [],
        prerequisite_role_ids: [],
        enabled: true,
        note: '',
      },
    ]);

  const updateDelegationPolicy = (
    index: number,
    changes: Partial<RoleDelegationPolicyPayload>
  ) => {
    setDelegationPolicies((prev) =>
      prev.map((policy, i) => (i === index ? { ...policy, ...changes } : policy))
    );
  };

  const removeDelegationPolicy = (index: number) => {
    setDelegationPolicies((prev) => prev.filter((_, i) => i !== index));
  };

  useEffect(() => {
    // AbortController to cancel requests if component unmounts during fetch
    const abortController = new AbortController();
    let isMounted = true;

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

        // Only update state if component is still mounted
        if (!isMounted) return;

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
        const normalizedPolicies = (settingsResponse.delegation_policies || []).map((p) => ({
          ...p,
          prerequisite_role_ids_all:
            p.prerequisite_role_ids_all ?? p.prerequisite_role_ids ?? [],
          prerequisite_role_ids_any: p.prerequisite_role_ids_any ?? [],
          prerequisite_role_ids: p.prerequisite_role_ids_all ?? p.prerequisite_role_ids ?? [],
        }));
        setDelegationPolicies(normalizedPolicies);
        setVoiceSelectableRoles(voiceSelectableResponse.selectable_roles || []);
        setVerificationChannelId(channelSettingsResponse.verification_channel_id);
        setBotSpamChannelId(channelSettingsResponse.bot_spam_channel_id);
        setPublicAnnouncementChannelId(channelSettingsResponse.public_announcement_channel_id);
        setLeadershipAnnouncementChannelId(channelSettingsResponse.leadership_announcement_channel_id);
        setOrganizationSid(orgSettingsResponse.organization_sid || '');
        setOrganizationName(orgSettingsResponse.organization_name || '');
        setOrgSidInput(orgSettingsResponse.organization_sid || '');
      } catch (err) {
        // Ignore errors from aborted requests
        if (!isMounted) return;
        handleApiError(err, 'Failed to load bot settings.');
        setError('Failed to load bot settings.');
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    };

    loadData();

    // Cleanup: mark as unmounted and abort any pending requests
    return () => {
      isMounted = false;
      abortController.abort();
    };
  }, [guildId]);

  const handleSaveAll = async () => {
    setSaving(true);
    setStatusMessage(null);
    setError(null);

    try {
      const cleanedPolicies = delegationPolicies
        .filter((p) => p.target_role_id)
        .map((p) => ({
          ...p,
          prerequisite_role_ids_all: p.prerequisite_role_ids_all ?? p.prerequisite_role_ids ?? [],
          prerequisite_role_ids_any: p.prerequisite_role_ids_any ?? [],
        }));

      const requestPayload = {
        roles: {
          bot_admins: botAdmins,
          discord_managers: discordManagers,
          moderators: moderators,
          staff: staff,
          bot_verified_role: botVerifiedRole,
          main_role: mainRole,
          affiliate_role: affiliateRole,
          nonmember_role: nonmemberRole,
          delegation_policies: cleanedPolicies,
        },
        channels: {
          verification_channel_id: verificationChannelId,
          bot_spam_channel_id: botSpamChannelId,
          public_announcement_channel_id: publicAnnouncementChannelId,
          leadership_announcement_channel_id: leadershipAnnouncementChannelId,
        },
        voice: { selectable_roles: voiceSelectableRoles },
        organization: {
          organization_sid: orgSidInput.trim() || null,
          organization_name: organizationName || null,
        },
      };

      const response = await guildApi.patchGuildConfig(guildId, requestPayload);
      const updated = response.data;

      // Roles
      setBotAdmins(updated.roles.bot_admins || []);
      setDiscordManagers(updated.roles.discord_managers || []);
      setModerators(updated.roles.moderators || []);
      setStaff(updated.roles.staff || []);
      setBotVerifiedRole(updated.roles.bot_verified_role || []);
      setMainRole(updated.roles.main_role || []);
      setAffiliateRole(updated.roles.affiliate_role || []);
      setNonmemberRole(updated.roles.nonmember_role || []);
      const normalizedUpdated = (updated.roles.delegation_policies || []).map((p) => ({
        ...p,
        prerequisite_role_ids_all:
          p.prerequisite_role_ids_all ?? p.prerequisite_role_ids ?? [],
        prerequisite_role_ids_any: p.prerequisite_role_ids_any ?? [],
        prerequisite_role_ids: p.prerequisite_role_ids_all ?? p.prerequisite_role_ids ?? [],
      }));
      setDelegationPolicies(normalizedUpdated);

      // Channels
      setVerificationChannelId(updated.channels.verification_channel_id);
      setBotSpamChannelId(updated.channels.bot_spam_channel_id);
      setPublicAnnouncementChannelId(updated.channels.public_announcement_channel_id);
      setLeadershipAnnouncementChannelId(updated.channels.leadership_announcement_channel_id);

      // Voice selectable roles
      setVoiceSelectableRoles(updated.voice.selectable_roles || []);

      // Organization
      setOrganizationSid(updated.organization.organization_sid || '');
      setOrganizationName(updated.organization.organization_name || '');
      setOrgSidInput(updated.organization.organization_sid || '');

      setStatusMessage('Settings saved and applied.');
    } catch (err) {
      handleApiError(err, 'Failed to save settings.');
      setError('Failed to save settings.');
    } finally {
      setSaving(false);
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
      handleApiError(err, 'Failed to validate organization SID. Please try again.');
      setOrgError('Failed to validate organization SID. Please try again.');
    } finally {
      setOrgValidating(false);
    }
  };

  if (loading) {
    return (
      <Card variant="default" className="animate-pulse">
        <CardBody>
          <div className="text-gray-400">Loading bot settings...</div>
        </CardBody>
      </Card>
    );
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
            <Card variant="default">
              <CardBody>
                <h5 className="text-sm font-semibold text-white mb-2">RSI Config</h5>
                <pre className="text-xs text-gray-300 whitespace-pre-wrap break-words">
                  {JSON.stringify(readOnly.rsi ?? {}, null, 2)}
                </pre>
              </CardBody>
            </Card>
            <Card variant="default">
              <CardBody>
                <h5 className="text-sm font-semibold text-white mb-2">Voice (Global)</h5>
                <pre className="text-xs text-gray-300 whitespace-pre-wrap break-words mb-2">
                  {JSON.stringify(readOnly.voice ?? {}, null, 2)}
                </pre>
                <div className="text-xs text-gray-200">
                  <span className="font-semibold">voice_debug_logging_enabled:</span>{' '}
                  <span>{String(readOnly.voice_debug_logging_enabled ?? false)}</span>
                </div>
              </CardBody>
            </Card>
          </div>
        </AccordionSection>
      )}

      {/* Status Messages */}
      {error && <Alert variant="error">{error}</Alert>}
      {statusMessage && <Alert variant="success">{statusMessage}</Alert>}
      {orgError && <Alert variant="error">{orgError}</Alert>}
      {orgStatusMessage && <Alert variant="success">{orgStatusMessage}</Alert>}

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
              <Input
                value={orgSidInput}
                onChange={(e) => setOrgSidInput(e.target.value.toUpperCase())}
                placeholder="Enter SID (e.g., TEST)"
                className="flex-1"
                maxLength={20}
              />
              <Button
                onClick={handleOrgValidate}
                disabled={orgValidating || !orgSidInput.trim()}
                variant="primary"
              >
                {orgValidating ? 'Validating...' : 'Validate'}
              </Button>
            </div>
          </div>

          {organizationName && (
            <Alert variant="success">
              <h5 className="text-sm font-semibold text-green-200 mb-1">Organization Found</h5>
              <p className="text-sm text-green-100">{organizationName}</p>
              <p className="text-xs text-green-300 mt-1">SID: {orgSidInput || organizationSid}</p>
            </Alert>
          )}

          <div className="flex justify-end pt-2 text-xs text-gray-400">
            Changes are saved with the main Save button below.
          </div>
        </div>
      </AccordionSection>

      {/* Assignable Roles - Top Level Accordion */}
      <AccordionSection title="📁 Assignable Roles" level={1}>
        <div className="space-y-4">
          {/* Bot Administration - Second Level Accordion */}
          <AccordionSection title="📁 Bot Administration" level={2}>
            <div className="space-y-4">
              <Alert variant="info" className="mb-4">
                <h5 className="text-sm font-semibold text-indigo-200 mb-1">Permission Hierarchy</h5>
                <p className="text-xs text-indigo-100">
                  Permissions are inherited from higher levels. Bot Admins have all permissions, 
                  Discord Managers can manage users, Moderators handle moderation, and Staff have basic access.
                </p>
                <div className="mt-2 text-xs text-indigo-200 font-mono">
                  Bot Owner &gt; Bot Admin &gt; Discord Manager &gt; Moderator &gt; Staff &gt; User
                </div>
              </Alert>

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

          <AccordionSection title="🤝 Delegated Role Grants" level={2}>
            <div className="space-y-4">
              <p className="text-xs text-gray-300">
                Define which roles can grant a target role and what prerequisites the target must already have.
                Disabled policies are ignored. Policies with no target role are not saved.
              </p>

              {delegationPolicies.map((policy, index) => (
                <Card key={index} variant="default" className="space-y-3">
                  <CardBody className="space-y-3">
                    <div className="flex items-center justify-between">
                      <h5 className="text-sm font-semibold text-white">Policy #{index + 1}</h5>
                      <div className="flex items-center gap-3">
                        <label className="flex items-center gap-2 text-xs text-gray-200">
                          <input
                            type="checkbox"
                            checked={policy.enabled}
                            onChange={(e) => updateDelegationPolicy(index, { enabled: e.target.checked })}
                            className="h-4 w-4 rounded border-slate-600 bg-slate-700 text-emerald-500 focus:ring-emerald-500"
                          />
                          Enabled
                        </label>
                        <Button
                          onClick={() => removeDelegationPolicy(index)}
                          variant="ghost"
                          size="sm"
                          className="text-red-300 hover:text-red-200"
                        >
                          Remove
                        </Button>
                      </div>
                    </div>

                  <div>
                    <h6 className="text-xs font-semibold text-white mb-1">Grantor Roles</h6>
                    <p className="text-[11px] text-gray-400 mb-2">Members must have at least one of these roles to grant the target role.</p>
                    <SearchableMultiSelect
                      options={roleOptions}
                      selected={policy.grantor_role_ids}
                      onChange={(val) => updateDelegationPolicy(index, { grantor_role_ids: val })}
                      placeholder="Select grantor roles"
                      componentId={`grantor-${index}`}
                    />
                  </div>

                  <div>
                    <h6 className="text-xs font-semibold text-white mb-1">Target Role</h6>
                    <p className="text-[11px] text-gray-400 mb-2">Role that will be granted when the policy passes.</p>
                    <SearchableSelect
                      options={roleOptions}
                      selected={policy.target_role_id || null}
                      onChange={(val) => updateDelegationPolicy(index, { target_role_id: val || '' })}
                      placeholder="Select target role"
                    />
                  </div>

                  <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                    <div>
                      <h6 className="text-xs font-semibold text-white mb-1">Must Have ALL</h6>
                      <p className="text-[11px] text-gray-400 mb-2">Target must already have every role listed here.</p>
                      <SearchableMultiSelect
                        options={roleOptions}
                        selected={policy.prerequisite_role_ids_all}
                        onChange={(val) =>
                          updateDelegationPolicy(index, {
                            prerequisite_role_ids_all: val,
                            prerequisite_role_ids: val,
                          })
                        }
                        placeholder="Select required roles (all)"
                        componentId={`prereq-all-${index}`}
                      />
                    </div>

                    <div>
                      <h6 className="text-xs font-semibold text-white mb-1">Must Have ANY</h6>
                      <p className="text-[11px] text-gray-400 mb-2">Target must have at least one of these roles.</p>
                      <SearchableMultiSelect
                        options={roleOptions}
                        selected={policy.prerequisite_role_ids_any}
                        onChange={(val) =>
                          updateDelegationPolicy(index, { prerequisite_role_ids_any: val })
                        }
                        placeholder="Select optional prerequisites (any)"
                        componentId={`prereq-any-${index}`}
                      />
                    </div>
                  </div>

                    <div>
                      <h6 className="text-xs font-semibold text-white mb-1">Note</h6>
                      <Input
                        value={policy.note ?? ''}
                        onChange={(e) => updateDelegationPolicy(index, { note: e.target.value })}
                        placeholder="Optional note"
                      />
                    </div>
                  </CardBody>
                </Card>
              ))}

              <Button onClick={addDelegationPolicy} variant="success">
                Add Delegation Policy
              </Button>
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

              <div className="flex justify-end text-xs text-gray-400">
                Changes are saved with the main Save button below.
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

          <div className="flex justify-end text-xs text-gray-400">
            Changes are saved with the main Save button below.
          </div>
        </div>
      </AccordionSection>

      {/* Save Button */}
      <div className="flex justify-end pt-4 border-t border-slate-700">
        <Button
          onClick={handleSaveAll}
          disabled={saving}
          variant="success"
          size="lg"
        >
          {saving ? 'Saving Changes...' : 'Save All Changes'}
        </Button>
      </div>
    </div>
  );
};

export default DashboardBotSettings;
