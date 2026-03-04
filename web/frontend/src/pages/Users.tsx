import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import {
  usersApi,
  authApi,
  adminApi,
  EnrichedUser,
  ExportUsersRequest,
  BulkRecheckResponse,
  BulkRecheckProgress,
  UserProfile,
  ALL_GUILDS_SENTINEL,
} from '../api/endpoints';
import { BulkRecheckResultsModal } from '../components/BulkRecheckResultsModal';
import { UserDetailsModal } from '../components/users/UserDetailsModal';
import { OrgBadgeList } from '../components/users/OrgBadgeList';
import { handleApiError } from '../utils/toast';
import { hasPermission } from '../utils/permissions';
import { getStatusVariant } from '../utils/statusHelpers';
import { Alert, Button, Card, Badge, Input, Pagination } from '../components/ui';

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

function Users() {
  // State
  const [users, setUsers] = useState<EnrichedUser[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeGuildId, setActiveGuildId] = useState<string | null>(null);
  const [userProfile, setUserProfile] = useState<UserProfile | null>(null);
  const [isCrossGuild, setIsCrossGuild] = useState(false);

  // Pagination
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);

  // Filters
  const [selectedStatuses, setSelectedStatuses] = useState<string[]>([]);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [debouncedSearch, setDebouncedSearch] = useState<string>('');
  const [selectedOrgs, setSelectedOrgs] = useState<string[]>([]);
  const [orgSearchQuery, setOrgSearchQuery] = useState<string>('');
  const [orgDropdownOpen, setOrgDropdownOpen] = useState<boolean>(false);
  const [statusDropdownOpen, setStatusDropdownOpen] = useState<boolean>(false);

  // Selection
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [selectAllFiltered, setSelectAllFiltered] = useState(false);
  const [excludedIds, setExcludedIds] = useState<Set<string>>(new Set());
  const headerCheckboxRef = useRef<HTMLInputElement | null>(null);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Admin actions
  const [recheckingUserId, setRecheckingUserId] = useState<string | null>(null);
  const [recheckSuccess, setRecheckSuccess] = useState<string | null>(null);
  const [bulkRechecking, setBulkRechecking] = useState(false);
  const [recheckProgress, setRecheckProgress] = useState<BulkRecheckProgress | null>(null);

  // Recheck results modal
  const [recheckResults, setRecheckResults] = useState<BulkRecheckResponse | null>(null);
  const [showResultsModal, setShowResultsModal] = useState(false);

  // User detail modal
  const [selectedUser, setSelectedUser] = useState<EnrichedUser | null>(null);
  const [showUserModal, setShowUserModal] = useState(false);



  const resetSelection = () => {
    setSelectAllFiltered(false);
    setSelectedIds(new Set());
    setExcludedIds(new Set());
  };

  const handleRecheckUser = async (userId: string) => {
    setRecheckingUserId(userId);
    setRecheckSuccess(null);
    setError(null);

    try {
      // Use bulk recheck endpoint for consistency (allows single user)
      const response = await adminApi.bulkRecheckUsers([userId]);

      // Show results modal
      setRecheckResults(response);
      setShowResultsModal(true);

      // Refresh the users list to show updated data
      await fetchUsers();
    } catch (err: any) {
      const status = err.response?.status;
      const message = status === 403 ? 'No access - moderator role required' : (err.response?.data?.detail || 'Failed to recheck user');
      setError(message);
    } finally {
      setRecheckingUserId(null);
    }
  };

  const handleBulkRecheck = async () => {
    if (!hasSelection) {
      setError('No users selected');
      return;
    }

    setBulkRechecking(true);
    setRecheckSuccess(null);
    setError(null);
    setRecheckProgress(null);

    try {
      // Resolve the list of user IDs to recheck.
      // When "select all filtered" is active the IDs are resolved
      // server-side so the recheck covers *all* matching DB rows,
      // not just the current page.
      let userIdsToRecheck: string[];
      if (selectAllFiltered) {
        const resolved = await usersApi.resolveFilteredIds({
          membership_statuses: normalizedStatusFilters.length > 0 ? normalizedStatusFilters : null,
          search: debouncedSearch || null,
          orgs: selectedOrgs.length > 0 ? selectedOrgs : null,
          exclude_ids: excludedIds.size > 0 ? Array.from(excludedIds) : null,
          limit: 100,
        });
        userIdsToRecheck = resolved.user_ids;

        if (resolved.total > 100) {
          setError(
            `${resolved.total} users match the current filters. ` +
            'Only the first 100 will be rechecked. Narrow your filters to target fewer users.',
          );
        }
      } else {
        // Only specifically selected users
        userIdsToRecheck = Array.from(selectedIds);
      }

      if (userIdsToRecheck.length === 0) {
        setError('No users selected');
        return;
      }

      if (userIdsToRecheck.length > 100) {
        setError('Cannot recheck more than 100 users at once');
        return;
      }

      // Kick off async bulk recheck and poll progress. If start endpoint is unavailable (404/405), fall back to synchronous flow.
      try {
        const startResp = await adminApi.startBulkRecheckUsers(userIdsToRecheck);

        const jobId = startResp.job_id;
        setRecheckProgress({
          job_id: jobId,
          total: userIdsToRecheck.length,
          processed: 0,
          successful: 0,
          failed: 0,
          status: 'running',
          current_user: null,
          final_response: null,
        });

        pollIntervalRef.current = setInterval(async () => {
          try {
            const progress = await adminApi.getBulkRecheckProgress(jobId);
            setRecheckProgress(progress);

            if (progress.status === 'complete' || progress.status === 'error') {
              if (pollIntervalRef.current) {
                clearInterval(pollIntervalRef.current);
                pollIntervalRef.current = null;
              }

              if (progress.final_response) {
                setRecheckResults(progress.final_response as BulkRecheckResponse);
                setShowResultsModal(true);
              }

              // Refresh users after completion
              await fetchUsers();

              // Clear selection and progress after showing results
              resetSelection();
              setBulkRechecking(false);
            }
          } catch (err) {
            if (pollIntervalRef.current) {
              clearInterval(pollIntervalRef.current);
              pollIntervalRef.current = null;
            }
            setBulkRechecking(false);
          }
        }, 1200);
      } catch (err: any) {
        const status = err?.response?.status;
        if (status === 404 || status === 405) {
          // Fallback to synchronous bulk recheck
          setRecheckProgress({
            job_id: 'sync',
            total: userIdsToRecheck.length,
            processed: 0,
            successful: 0,
            failed: 0,
            status: 'running',
            current_user: null,
            final_response: null,
          });

          const resp = await adminApi.bulkRecheckUsers(userIdsToRecheck);

          setRecheckProgress({
            job_id: 'sync',
            total: resp.total,
            processed: resp.total,
            successful: resp.successful,
            failed: resp.failed,
            status: 'complete',
            current_user: null,
            final_response: resp,
          });

          setRecheckResults(resp);
          setShowResultsModal(true);
          await fetchUsers();
          resetSelection();
          setBulkRechecking(false);
        } else {
          throw err;
        }
      }

    } catch (err: any) {
      const status = err.response?.status;
      const message = status === 403 ? 'No access - moderator role required' : (err.response?.data?.detail || 'Failed to bulk recheck users');
      setError(message);
      setRecheckProgress(null);
      setBulkRechecking(false);
    }
  };

  const normalizedStatusFilters = useMemo(() => {
    return selectedStatuses
      .filter((status) => status && status !== 'all')
      .map((status) => status.toLowerCase());
  }, [selectedStatuses]);

  // Fetch available orgs from the API (all orgs across the full dataset)
  const [availableOrgs, setAvailableOrgs] = useState<string[]>([]);
  useEffect(() => {
    if (!activeGuildId) return;
    let cancelled = false;
    usersApi.getAvailableOrgs().then(data => {
      if (!cancelled) setAvailableOrgs(data.orgs);
    }).catch(() => { /* ignore — org dropdown will be empty */ });
    return () => { cancelled = true; };
  }, [activeGuildId]);

  // Filter orgs by search query
  const filteredAvailableOrgs = useMemo(() => {
    if (!orgSearchQuery.trim()) {
      return availableOrgs;
    }
    const query = orgSearchQuery.toLowerCase().trim();
    return availableOrgs.filter(org => org.toLowerCase().includes(query));
  }, [availableOrgs, orgSearchQuery]);

  // Server-side filtering: users are already filtered by the API.
  // Client-side filteredUsers is kept as a stable reference for selection logic.
  const filteredUsers = users;

  // Export state
  const [exporting, setExporting] = useState(false);

  // Debounce search input (300ms) so we don't hit the API on every keystroke
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchQuery);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  // Reset to page 1 when server-side filters change
  const isInitialMount = useRef(true);
  useEffect(() => {
    if (isInitialMount.current) {
      isInitialMount.current = false;
      return;
    }
    setPage(1);
    resetSelection();
  }, [debouncedSearch, selectedOrgs]);

  // Close filter dropdowns when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as HTMLElement;

      if (orgDropdownOpen) {
        if (!target.closest('.org-dropdown-container')) {
          setOrgDropdownOpen(false);
        }
      }

      if (statusDropdownOpen) {
        if (!target.closest('.status-dropdown-container')) {
          setStatusDropdownOpen(false);
        }
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [orgDropdownOpen, statusDropdownOpen]);

  // Cleanup interval on unmount to prevent memory leaks
  useEffect(() => {
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
    };
  }, []);

  // Load user profile to get active guild
  useEffect(() => {
    const loadUserProfile = async () => {
      try {
        const response = await authApi.getMe();
        setUserProfile(response.user);
        setActiveGuildId(response.user?.active_guild_id || null);
      } catch (err) {
        handleApiError(err, 'Failed to load user profile');
      }
    };

    loadUserProfile();
  }, []);

  // Check if user has moderator access (required for recheck operations)
  const canRecheck = useMemo(() => {
    if (!userProfile?.active_guild_id || !userProfile.authorized_guilds) {
      return false;
    }
    const guildPerm = userProfile.authorized_guilds[userProfile.active_guild_id];
    return guildPerm && hasPermission(guildPerm.role_level, 'moderator');
  }, [userProfile]);



  useEffect(() => {
    if (!activeGuildId) {
      return;
    }
    setPage(1);
    resetSelection();
    // Check if we're in cross-guild mode
    setIsCrossGuild(activeGuildId === ALL_GUILDS_SENTINEL);
  }, [activeGuildId]);

  // Fetch users
  const fetchUsers = useCallback(async () => {
    if (!activeGuildId) {
      setUsers([]);
      setTotal(0);
      setTotalPages(0);
      setIsCrossGuild(false);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const data = await usersApi.getUsers(
        page,
        pageSize,
        normalizedStatusFilters.length > 0 ? normalizedStatusFilters : null,
        debouncedSearch || null,
        selectedOrgs.length > 0 ? selectedOrgs : null,
      );
      setUsers(data.items);
      setTotal(data.total);
      setTotalPages(data.total_pages);
      setIsCrossGuild(data.is_cross_guild === true);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load users');
      setUsers([]);
      setTotal(0);
      setTotalPages(0);
    } finally {
      setLoading(false);
    }
  }, [activeGuildId, page, pageSize, normalizedStatusFilters, debouncedSearch, selectedOrgs]);

  // Load users on mount and when filters/pagination change
  useEffect(() => {
    fetchUsers();
  }, [page, pageSize, normalizedStatusFilters, activeGuildId, debouncedSearch, selectedOrgs]);

  // Keep modal user details in sync with latest table data after refreshes/rechecks
  useEffect(() => {
    if (!showUserModal || !selectedUser) {
      return;
    }

    const updatedUser = users.find((user) => user.discord_id === selectedUser.discord_id);
    if (updatedUser) {
      setSelectedUser(updatedUser);
    }
  }, [users, showUserModal, selectedUser]);

  // Refresh modal user details on open to backfill occasionally-missing enriched fields
  useEffect(() => {
    if (!showUserModal || !selectedUser?.discord_id) {
      return;
    }

    let cancelled = false;

    const refreshModalUserDetails = async () => {
      try {
        const response = await usersApi.getUserDetails(selectedUser.discord_id);
        const refreshedUser = response.data;

        if (cancelled) {
          return;
        }

        setSelectedUser((current) => {
          if (!current || current.discord_id !== refreshedUser.discord_id) {
            return current;
          }

          return {
            ...current,
            ...refreshedUser,
            roles: refreshedUser.roles.length > 0 ? refreshedUser.roles : current.roles,
            main_orgs:
              refreshedUser.main_orgs && refreshedUser.main_orgs.length > 0
                ? refreshedUser.main_orgs
                : current.main_orgs,
            affiliate_orgs:
              refreshedUser.affiliate_orgs && refreshedUser.affiliate_orgs.length > 0
                ? refreshedUser.affiliate_orgs
                : current.affiliate_orgs,
            joined_at: refreshedUser.joined_at ?? current.joined_at,
            created_at: refreshedUser.created_at ?? current.created_at,
            last_updated: refreshedUser.last_updated ?? current.last_updated,
          };
        });
      } catch {
        // Best-effort refresh only; keep existing modal snapshot on failure.
      }
    };

    refreshModalUserDetails();

    return () => {
      cancelled = true;
    };
  }, [showUserModal, selectedUser?.discord_id]);



  // Filter handlers
  const toggleStatus = (status: string) => {
    setSelectedStatuses(prev =>
      prev.includes(status)
        ? prev.filter(s => s !== status)
        : [...prev, status]
    );
    setPage(1);
    resetSelection();
  };

  const clearFilters = () => {
    setSelectedStatuses([]);
    setSearchQuery('');
    setSelectedOrgs([]);
    setOrgSearchQuery('');
    setPage(1);
    resetSelection();
  };

  const toggleOrg = (org: string) => {
    setSelectedOrgs(prev =>
      prev.includes(org)
        ? prev.filter(o => o !== org)
        : [...prev, org]
    );
    // Page reset handled by the debouncedSearch/selectedOrgs effect
  };


  // Selection handlers
  const handleSelectUser = (userId: string) => {
    if (selectAllFiltered) {
      setExcludedIds((prev) => {
        const next = new Set(prev);
        if (next.has(userId)) {
          next.delete(userId);
        } else {
          next.add(userId);
        }
        return next;
      });
    } else {
      setSelectedIds((prev) => {
        const next = new Set(prev);
        if (next.has(userId)) {
          next.delete(userId);
        } else {
          next.add(userId);
        }
        return next;
      });
    }
  };

  const handleSelectAllOnPage = () => {
    if (filteredUsers.length === 0) {
      return;
    }

    if (selectAllFiltered) {
      const allPageSelected = filteredUsers.every((user) => !excludedIds.has(user.discord_id));
      setExcludedIds((prev) => {
        const next = new Set(prev);
        if (allPageSelected) {
          filteredUsers.forEach((user) => next.add(user.discord_id));
        } else {
          filteredUsers.forEach((user) => next.delete(user.discord_id));
        }
        return next;
      });
    } else {
      const allPageSelected = filteredUsers.every((user) => selectedIds.has(user.discord_id));
      setSelectedIds((prev) => {
        const next = new Set(prev);
        if (allPageSelected) {
          filteredUsers.forEach((user) => next.delete(user.discord_id));
        } else {
          filteredUsers.forEach((user) => next.add(user.discord_id));
        }
        return next;
      });
    }
  };

  const handleSelectAllFiltered = () => {
    if (total === 0) {
      return;
    }
    setSelectAllFiltered(true);
    setSelectedIds(new Set());
    setExcludedIds(new Set());
  };

  const selectedCount = selectAllFiltered
    ? Math.max(total - excludedIds.size, 0)
    : selectedIds.size;

  const hasSelection = selectAllFiltered
    ? selectedCount > 0
    : selectedIds.size > 0;

  const selectionSummary = useMemo(() => {
    if (selectAllFiltered) {
      if (selectedCount === 0) {
        return 'No users available for the current filters';
      }
      if (excludedIds.size > 0) {
        return `All ${selectedCount} filtered user(s) selected (${excludedIds.size} excluded)`;
      }
      return `All ${selectedCount} filtered user(s) selected`;
    }

    if (selectedIds.size > 0) {
      return `${selectedIds.size} user(s) selected`;
    }

    return `${total} total user(s)`;
  }, [selectAllFiltered, selectedCount, excludedIds, selectedIds, total]);

  const pageSelectionInfo = useMemo(() => {
    if (filteredUsers.length === 0) {
      return { allSelected: false, partiallySelected: false };
    }

    let selectedOnPage = 0;
    filteredUsers.forEach((user) => {
      const isSelected = selectAllFiltered
        ? !excludedIds.has(user.discord_id)
        : selectedIds.has(user.discord_id);
      if (isSelected) {
        selectedOnPage += 1;
      }
    });

    return {
      allSelected: selectedOnPage === filteredUsers.length,
      partiallySelected:
        selectedOnPage > 0 && selectedOnPage < filteredUsers.length,
    };
  }, [filteredUsers, selectAllFiltered, excludedIds, selectedIds]);

  useEffect(() => {
    if (!headerCheckboxRef.current) {
      return;
    }
    headerCheckboxRef.current.indeterminate = pageSelectionInfo.partiallySelected;
  }, [pageSelectionInfo]);

  // Export handlers
  const handleExportSelected = async () => {
    if (!hasSelection) {
      setError('No users selected');
      return;
    }

    setExporting(true);
    try {
      const request: ExportUsersRequest = buildExportFilters();

      if (selectAllFiltered) {
        if (excludedIds.size > 0) {
          request.exclude_ids = Array.from(excludedIds);
        }
      } else {
        request.selected_ids = Array.from(selectedIds);
      }

      await usersApi.exportUsers(request);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to export users');
    } finally {
      setExporting(false);
    }
  };

  const handleExportFiltered = async () => {
    setExporting(true);
    try {
      const request = buildExportFilters();
      await usersApi.exportUsers(request);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to export users');
    } finally {
      setExporting(false);
    }
  };

  // Pagination handlers
  const handlePrevPage = () => {
    if (page > 1) setPage(page - 1);
  };

  const handleNextPage = () => {
    if (page < totalPages) setPage(page + 1);
  };

  const buildExportFilters = (): ExportUsersRequest => {
    const payload: ExportUsersRequest = {};

    if (normalizedStatusFilters.length === 1) {
      payload.membership_status = normalizedStatusFilters[0];
    }
    if (normalizedStatusFilters.length > 0) {
      payload.membership_statuses = normalizedStatusFilters;
    }
    if (debouncedSearch.trim()) {
      payload.search = debouncedSearch.trim();
    }
    if (selectedOrgs.length > 0) {
      payload.orgs = selectedOrgs;
    }

    return payload;
  };

  const startRecord = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const endRecord = total === 0 ? 0 : Math.min(page * pageSize, total);

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">Members</h2>

      {/* Success Message */}
      {recheckSuccess && (
        <Alert variant="success" className="mb-6">
          {recheckSuccess}
        </Alert>
      )}

      {/* Filter Bar */}
      <Card padding="md" className="mb-6">
        <div className="flex flex-wrap gap-4 items-start">
          {/* Search Box */}
          <div className="flex-1 min-w-[250px]">
            <label className="block text-sm font-medium text-gray-400 mb-2">
              Search
            </label>
            <Input
              placeholder="Search by username, RSI handle, or UUID..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>

          {/* Organization Filter */}
          <div className="flex-1 min-w-[250px] relative org-dropdown-container">
            <label className="block text-sm font-medium text-gray-400 mb-2">
              Organizations {selectedOrgs.length > 0 && `(${selectedOrgs.length} selected)`}
            </label>
            <div className="relative">
              <div
                className="w-full bg-slate-900 border border-slate-600 rounded px-4 py-2 text-white cursor-pointer hover:border-slate-500 transition-colors min-h-[42px] flex items-center justify-between"
                onClick={() => setOrgDropdownOpen(!orgDropdownOpen)}
              >
                <div className="flex flex-wrap gap-1 flex-1 min-h-[26px]">
                  {selectedOrgs.length === 0 ? (
                    <span className="text-gray-500">All Organizations</span>
                  ) : (
                    selectedOrgs.map(org => (
                      <span
                        key={org}
                        className="px-2 py-0.5 text-xs rounded bg-indigo-900/30 text-indigo-300 border border-indigo-700/50 flex items-center gap-1"
                        onClick={(e) => {
                          e.stopPropagation();
                          toggleOrg(org);
                        }}
                      >
                        {org}
                        <span className="hover:text-indigo-100">×</span>
                      </span>
                    ))
                  )}
                </div>
                <span className="text-gray-400 ml-2">{orgDropdownOpen ? '▲' : '▼'}</span>
              </div>

              {orgDropdownOpen && (
                <div className="absolute z-10 w-full mt-1 bg-slate-900 border border-slate-600 rounded shadow-lg max-h-64 overflow-hidden">
                  <div className="p-2 border-b border-slate-700">
                    <input
                      type="text"
                      placeholder="Search organizations..."
                      value={orgSearchQuery}
                      onChange={(e) => setOrgSearchQuery(e.target.value)}
                      onClick={(e) => e.stopPropagation()}
                      className="w-full bg-slate-800 border border-slate-600 rounded px-3 py-1.5 text-white text-sm placeholder-gray-500 focus:outline-none focus:border-indigo-500"
                    />
                  </div>
                  <div className="max-h-48 overflow-y-auto">
                    {filteredAvailableOrgs.length === 0 ? (
                      <div className="px-4 py-3 text-sm text-gray-500">No organizations found</div>
                    ) : (
                      filteredAvailableOrgs.map(org => (
                        <label
                          key={org}
                          className="flex items-center px-4 py-2 hover:bg-slate-800 cursor-pointer text-white text-sm"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <input
                            type="checkbox"
                            checked={selectedOrgs.includes(org)}
                            onChange={() => toggleOrg(org)}
                            className="mr-3 h-4 w-4 text-indigo-600 focus:ring-indigo-500 border-slate-600 rounded"
                          />
                          {org}
                        </label>
                      ))
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Membership Status Multi-Select */}
          <div className="flex-1 min-w-[250px] relative status-dropdown-container">
            <label className="block text-sm font-medium text-gray-400 mb-2">
              Membership Status {selectedStatuses.length > 0 && `(${selectedStatuses.length} selected)`}
            </label>
            <div className="relative">
              <div
                className="w-full bg-slate-900 border border-slate-600 rounded px-4 py-2 text-white cursor-pointer hover:border-slate-500 transition-colors min-h-[42px] flex items-center justify-between"
                onClick={() => setStatusDropdownOpen(!statusDropdownOpen)}
              >
                <div className="flex flex-wrap gap-1 flex-1 min-h-[26px]">
                  {selectedStatuses.length === 0 ? (
                    <span className="text-gray-500">All Statuses</span>
                  ) : (
                    selectedStatuses.map(status => (
                      <button
                        key={status}
                        type="button"
                        className="px-2 py-0.5 text-xs rounded bg-indigo-900/30 text-indigo-300 border border-indigo-700/50 flex items-center gap-1 hover:bg-indigo-900/50 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                        onClick={(e) => {
                          e.stopPropagation();
                          toggleStatus(status);
                        }}
                        aria-label={`Remove ${status.replace('_', ' ')} status filter`}
                      >
                        {status.replace('_', ' ')}
                        <span className="hover:text-indigo-100" aria-hidden="true">×</span>
                      </button>
                    ))
                  )}
                </div>
                <span className="text-gray-400 ml-2">{statusDropdownOpen ? '▲' : '▼'}</span>
              </div>

              {statusDropdownOpen && (
                <div className="absolute z-10 w-full mt-1 bg-slate-900 border border-slate-600 rounded shadow-lg max-h-64 overflow-hidden">
                  <div className="max-h-48 overflow-y-auto">
                    {['main', 'affiliate', 'non_member', 'unknown'].map(status => (
                      <label
                        key={status}
                        className="flex items-center px-4 py-2 hover:bg-slate-800 cursor-pointer text-white text-sm"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <input
                          type="checkbox"
                          checked={selectedStatuses.includes(status)}
                          onChange={() => toggleStatus(status)}
                          className="mr-3 h-4 w-4 text-indigo-600 focus:ring-indigo-500 border-slate-600 rounded"
                        />
                        <span className="capitalize">{status.replace('_', ' ')}</span>
                      </label>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Clear Filters Button */}
          {(selectedStatuses.length > 0 || searchQuery.trim() || selectedOrgs.length > 0) && (
            <div className="self-end">
              <Button
                variant="secondary"
                onClick={clearFilters}
              >
                Clear Filters
              </Button>
            </div>
          )}

          {/* Page Size Selector */}
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-2">
              Per Page
            </label>
            <select
              value={pageSize}
              onChange={(e) => {
                setPageSize(Number(e.target.value));
                setPage(1);
              }}
              className="bg-slate-900 border border-slate-600 rounded px-4 py-2 text-white focus:outline-none focus:border-indigo-500"
            >
              <option value={10}>10</option>
              <option value={25}>25</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
            </select>
          </div>
        </div>
      </Card>

      {/* Cross-Guild Mode Alert */}
      {isCrossGuild && (
        <Alert variant="info" className="mb-6">
          <strong>🌐 All Guilds Mode</strong> — Viewing users across all servers.
          Bulk actions are disabled in cross-guild view. Switch to a specific server to perform actions.
        </Alert>
      )}

      {/* Export Bar - Hide bulk actions in cross-guild mode */}
      {(total > 0 || hasSelection) && !isCrossGuild && (
        <Card padding="md" className="mb-6">
          <div className="flex flex-wrap gap-4 justify-between items-center">
            <div>
              <div className="text-sm text-gray-300">{selectionSummary}</div>
              <div className="flex gap-2 mt-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleSelectAllFiltered}
                  disabled={selectAllFiltered || total === 0}
                  className="border border-slate-600"
                >
                  Select All Filtered
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={resetSelection}
                  disabled={!hasSelection}
                  className="border border-slate-600"
                >
                  Clear Selection
                </Button>
              </div>
            </div>
            <div className="flex gap-3">
              {/* Progress Overlay */}
              {recheckProgress && recheckProgress.status === 'running' && (
                <div className="flex items-center gap-2 px-4 py-2 bg-blue-900/50 border border-blue-500 rounded-lg">
                  <svg className="animate-spin h-4 w-4 text-blue-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  <span className="text-blue-300 text-sm font-medium">
                    Checking {recheckProgress.processed}/{recheckProgress.total}...
                  </span>
                </div>
              )}
              {canRecheck && (
                <Button
                  onClick={handleBulkRecheck}
                  loading={bulkRechecking}
                  disabled={!hasSelection}
                  title="Re-verify selected users' RSI membership and update roles"
                >
                  {bulkRechecking ? 'Rechecking...' : 'Recheck Selected'}
                </Button>
              )}
              <Button
                variant="success"
                onClick={handleExportSelected}
                loading={exporting}
                disabled={!hasSelection}
              >
                {exporting ? 'Exporting...' : 'Export Selected'}
              </Button>
              <Button
                variant="secondary"
                onClick={handleExportFiltered}
                loading={exporting}
                className="bg-blue-600 hover:bg-blue-700"
              >
                {exporting ? 'Exporting...' : 'Export All Filtered'}
              </Button>
            </div>
          </div>
        </Card>
      )}

      {/* Error */}
      {error && (
        <Alert variant="error" className="mb-6">
          {error}
        </Alert>
      )}

      {/* Loading Skeleton */}
      {loading && (
        <Card padding="lg">
          <div className="animate-pulse space-y-4">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="h-16 bg-slate-700 rounded"></div>
            ))}
          </div>
        </Card>
      )}

      {/* Users Table */}
      {!loading && filteredUsers.length > 0 && (
        <div className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-slate-900">
                <tr>
                  {/* Hide checkbox column in cross-guild mode (no bulk actions) */}
                  {!isCrossGuild && (
                    <th className="px-2 sm:px-3 py-2 text-left w-10">
                      <input
                        ref={headerCheckboxRef}
                        type="checkbox"
                        checked={filteredUsers.length > 0 && pageSelectionInfo.allSelected}
                        onChange={handleSelectAllOnPage}
                        className="rounded border-slate-600 bg-slate-800 text-indigo-600 focus:ring-indigo-500"
                      />
                    </th>
                  )}
                  {/* Show guild column in cross-guild mode */}
                  {isCrossGuild && (
                    <th className="px-2 sm:px-3 py-2 text-left text-xs font-medium text-gray-400 uppercase hidden sm:table-cell">
                      Guild
                    </th>
                  )}
                  <th className="px-2 sm:px-3 py-2 text-left text-xs font-medium text-gray-400 uppercase">
                    Member
                  </th>
                  <th className="px-2 sm:px-3 py-2 text-left text-xs font-medium text-gray-400 uppercase">
                    Status
                  </th>
                  <th className="hidden lg:table-cell px-3 py-2 text-left text-xs font-medium text-gray-400 uppercase">
                    Main Org
                  </th>
                  <th className="hidden lg:table-cell px-3 py-2 text-left text-xs font-medium text-gray-400 uppercase">
                    Affiliate Orgs
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700">
                {filteredUsers.map((user) => {
                  const isRowSelected = selectAllFiltered
                    ? !excludedIds.has(user.discord_id)
                    : selectedIds.has(user.discord_id);

                  return (
                    <tr
                      key={user.discord_id}
                      className="hover:bg-slate-700/50 transition-colors"
                    >
                    {/* Hide checkbox in cross-guild mode */}
                    {!isCrossGuild && (
                      <td className="px-2 sm:px-3 py-2 w-10">
                        <input
                          type="checkbox"
                          checked={isRowSelected}
                          onChange={() => handleSelectUser(user.discord_id)}
                          className="rounded border-slate-600 bg-slate-800 text-indigo-600 focus:ring-indigo-500"
                        />
                      </td>
                    )}
                    {/* Show guild in cross-guild mode */}
                    {isCrossGuild && (
                      <td className="hidden sm:table-cell px-2 sm:px-3 py-2">
                        <Badge variant="purple" className="text-xs">
                          {user.guild_name || user.guild_id || 'Unknown'}
                        </Badge>
                      </td>
                    )}
                    <td className="px-2 sm:px-3 py-2">
                      <button
                        type="button"
                        className="w-full text-left rounded px-1 py-1 -mx-1 -my-1 hover:bg-slate-700/40 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                        onClick={() => {
                          setSelectedUser(user);
                          setShowUserModal(true);
                        }}
                        aria-label={`View details for ${user.global_name || user.username}`}
                      >
                        <div className="flex items-center gap-2">
                          {user.avatar_url ? (
                            <img
                              src={user.avatar_url}
                              alt={user.username}
                              className="w-7 h-7 sm:w-8 sm:h-8 rounded-full flex-shrink-0"
                            />
                          ) : (
                            <div className="w-7 h-7 sm:w-8 sm:h-8 rounded-full bg-slate-700 flex items-center justify-center text-gray-400 text-sm font-bold flex-shrink-0">
                              {user.username.charAt(0).toUpperCase()}
                            </div>
                          )}
                          <div className="min-w-0">
                            <div className="text-sm font-medium text-white truncate">
                              {user.global_name || user.username}
                            </div>
                            <div className="text-xs text-gray-400 truncate">
                              {user.username}
                            </div>
                            <div className="text-[11px] text-gray-500 truncate lg:hidden mt-0.5">
                              Main: {user.main_orgs?.[0] || '-'} · Aff: {user.affiliate_orgs?.[0] || '-'}
                            </div>
                          </div>
                        </div>
                      </button>
                    </td>
                    <td className="px-2 sm:px-3 py-2">
                      <Badge variant={getStatusVariant(user.membership_status)} className="text-xs">
                        {user.membership_status || 'unknown'}
                      </Badge>
                    </td>
                    <td className="hidden lg:table-cell px-3 py-2 text-sm text-gray-300">
                      <OrgBadgeList orgs={user.main_orgs} maxVisible={2} colorScheme="blue" />
                    </td>
                    <td className="hidden lg:table-cell px-3 py-2 text-sm text-gray-300">
                      <OrgBadgeList orgs={user.affiliate_orgs} maxVisible={2} colorScheme="green" />
                    </td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="px-3 sm:px-6 py-4 bg-slate-900 border-t border-slate-700">
            <Pagination
              page={page}
              totalPages={totalPages}
              onPrevious={handlePrevPage}
              onNext={handleNextPage}
              summary={
                total === 0
                  ? 'No results to display'
                  : `Showing ${startRecord} to ${endRecord} of ${total} results`
              }
            />
          </div>
        </div>
      )}

      {/* Empty State */}
      {!loading && filteredUsers.length === 0 && (
        <Card padding="lg" className="text-center py-12">
          <div className="text-gray-400 text-lg">
            {searchQuery.trim() ? 'No members match your search' : 'No members found'}
          </div>
          <div className="text-gray-500 text-sm mt-2">
            {searchQuery.trim()
              ? 'Try a different search term or clear your filters'
              : 'Try adjusting your filters or check back later'
            }
          </div>
        </Card>
      )}

      {/* User Detail Modal */}
      <UserDetailsModal
        open={showUserModal}
        user={selectedUser}
        isCrossGuild={isCrossGuild}
        onClose={() => {
          setShowUserModal(false);
          setSelectedUser(null);
        }}
        canRecheck={canRecheck}
        recheckingUserId={recheckingUserId}
        onRecheck={handleRecheckUser}
        canViewMetrics={canRecheck}
      />

      {/* Recheck Results Modal */}
      {recheckResults && (
        <BulkRecheckResultsModal
          open={showResultsModal}
          onClose={() => {
            setShowResultsModal(false);
            setRecheckResults(null);
          }}
          results={recheckResults}
        />
      )}
    </div>
  );
}

export default Users;
