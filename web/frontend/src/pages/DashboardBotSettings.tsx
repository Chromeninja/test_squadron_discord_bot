import { useEffect, useMemo, useState } from 'react';
import { guildApi, GuildRole, DiscordChannel } from '../api/endpoints';
import SearchableMultiSelect, { MultiSelectOption } from '../components/SearchableMultiSelect';
import SearchableSelect, { SelectOption } from '../components/SearchableSelect';
import AccordionSection from '../components/AccordionSection';

interface DashboardBotSettingsProps {
  guildId: string;
}

const DashboardBotSettings = ({ guildId }: DashboardBotSettingsProps) => {
  const [roles, setRoles] = useState<GuildRole[]>([]);
  const [channels, setChannels] = useState<DiscordChannel[]>([]);
  const [botAdmins, setBotAdmins] = useState<number[]>([]);
  const [leadModerators, setLeadModerators] = useState<number[]>([]);
  const [mainRole, setMainRole] = useState<number[]>([]);
  const [affiliateRole, setAffiliateRole] = useState<number[]>([]);
  const [nonmemberRole, setNonmemberRole] = useState<number[]>([]);
  const [voiceSelectableRoles, setVoiceSelectableRoles] = useState<number[]>([]);
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

  const roleOptions: MultiSelectOption[] = useMemo(
    () => roles.map((role) => ({ id: role.id, name: role.name })),
    [roles]
  );

  const channelOptions: SelectOption[] = useMemo(
    () =>
      channels.map((channel) => ({
        id: channel.id,
        name: channel.name,
        category: channel.category,
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
        const [rolesResponse, settingsResponse, voiceSelectableResponse, channelsResponse, channelSettingsResponse] = await Promise.all([
          guildApi.getDiscordRoles(guildId),
          guildApi.getBotRoleSettings(guildId),
          guildApi.getVoiceSelectableRoles(guildId),
          guildApi.getDiscordChannels(guildId),
          guildApi.getBotChannelSettings(guildId),
        ]);

        setRoles(rolesResponse.roles);
        setChannels(channelsResponse.channels);
        setBotAdmins(settingsResponse.bot_admins);
        setLeadModerators(settingsResponse.lead_moderators);
        setMainRole(settingsResponse.main_role || []);
        setAffiliateRole(settingsResponse.affiliate_role || []);
        setNonmemberRole(settingsResponse.nonmember_role || []);
        setVoiceSelectableRoles(voiceSelectableResponse.selectable_roles || []);
        setVerificationChannelId(channelSettingsResponse.verification_channel_id);
        setBotSpamChannelId(channelSettingsResponse.bot_spam_channel_id);
        setPublicAnnouncementChannelId(channelSettingsResponse.public_announcement_channel_id);
        setLeadershipAnnouncementChannelId(channelSettingsResponse.leadership_announcement_channel_id);
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
      const payload = {
        bot_admins: botAdmins,
        lead_moderators: leadModerators,
        main_role: mainRole,
        affiliate_role: affiliateRole,
        nonmember_role: nonmemberRole,
      };
      const updated = await guildApi.updateBotRoleSettings(guildId, payload);
      setBotAdmins(updated.bot_admins);
      setLeadModerators(updated.lead_moderators);
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
      const updated = await guildApi.updateVoiceSelectableRoles(guildId, {
        selectable_roles: voiceSelectableRoles,
      });
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
      const payload = {
        verification_channel_id: verificationChannelId,
        bot_spam_channel_id: botSpamChannelId,
        public_announcement_channel_id: publicAnnouncementChannelId,
        leadership_announcement_channel_id: leadershipAnnouncementChannelId,
      };
      const updated = await guildApi.updateBotChannelSettings(guildId, payload);
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

  if (loading) {
    return <div className="text-gray-400">Loading bot settings...</div>;
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-3xl font-bold text-white">Role Configuration</h2>
        <p className="mt-2 text-gray-400">
          Configure Discord roles for bot permissions and member categories.
        </p>
      </div>

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

      {/* Assignable Roles - Top Level Accordion */}
      <AccordionSection title="📁 Assignable Roles" level={1}>
        <div className="space-y-4">
          {/* Bot Administration - Second Level Accordion */}
          <AccordionSection title="📁 Bot Administration" level={2}>
            <div className="space-y-4">
              <div>
                <h5 className="text-sm font-semibold text-white mb-1">Bot Admin Roles</h5>
                <p className="text-xs text-gray-400 mb-2">
                  Users with these roles have full bot administration access.
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
                <h5 className="text-sm font-semibold text-white mb-1">Lead Moderator Roles</h5>
                <p className="text-xs text-gray-400 mb-2">
                  Users with these roles have elevated moderation permissions.
                </p>
                <SearchableMultiSelect
                  options={roleOptions}
                  selected={leadModerators}
                  onChange={setLeadModerators}
                  placeholder="Search and select moderator roles"
                  componentId="lead-mods"
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
