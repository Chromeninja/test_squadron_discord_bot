import { useEffect, useMemo, useRef, useState } from 'react';
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
import { handleApiError } from '../utils/toast';
import { hasPermission } from '../utils/permissions';
import { Alert, Button, Card, Badge, Input } from '../components/ui';

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
  const [selectedOrgs, setSelectedOrgs] = useState<string[]>([]);
  const [orgSearchQuery, setOrgSearchQuery] = useState<string>('');
  const [orgDropdownOpen, setOrgDropdownOpen] = useState<boolean>(false);
  
  // Selection
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [selectAllFiltered, setSelectAllFiltered] = useState(false);
  const [excludedIds, setExcludedIds] = useState<Set<string>>(new Set());
  const headerCheckboxRef = useRef<HTMLInputElement | null>(null);
  
  // Admin actions
  const [recheckingUserId, setRecheckingUserId] = useState<string | null>(null);
  const [recheckSuccess, setRecheckSuccess] = useState<string | null>(null);
  const [bulkRechecking, setBulkRechecking] = useState(false);
  const [recheckProgress, setRecheckProgress] = useState<BulkRecheckProgress | null>(null);
  
  // Recheck results modal
  const [recheckResults, setRecheckResults] = useState<BulkRecheckResponse | null>(null);
  const [showResultsModal, setShowResultsModal] = useState(false);

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
      // Get the list of selected user IDs
      let userIdsToRecheck: string[];
      if (selectAllFiltered) {
        // All filtered users except excluded ones
        userIdsToRecheck = filteredUsers
          .filter(u => !excludedIds.has(u.discord_id))
          .map(u => u.discord_id);
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
      let pollInterval: ReturnType<typeof setInterval> | null = null;
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

        pollInterval = setInterval(async () => {
          try {
            const progress = await adminApi.getBulkRecheckProgress(jobId);
            setRecheckProgress(progress);

            if (progress.status === 'complete' || progress.status === 'error') {
              if (pollInterval) {
                clearInterval(pollInterval);
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
            if (pollInterval) {
              clearInterval(pollInterval);
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
  
  // Get unique organizations from all users
  const availableOrgs = useMemo(() => {
    const orgSet = new Set<string>();
    users.forEach(user => {
      user.main_orgs?.forEach(org => {
        if (org && org !== 'REDACTED') orgSet.add(org);
      });
      user.affiliate_orgs?.forEach(org => {
        if (org && org !== 'REDACTED') orgSet.add(org);
      });
    });
    return Array.from(orgSet).sort();
  }, [users]);
  
  // Filter orgs by search query
  const filteredAvailableOrgs = useMemo(() => {
    if (!orgSearchQuery.trim()) {
      return availableOrgs;
    }
    const query = orgSearchQuery.toLowerCase().trim();
    return availableOrgs.filter(org => org.toLowerCase().includes(query));
  }, [availableOrgs, orgSearchQuery]);
  
  // Filter users by search query and orgs (client-side)
  const filteredUsers = useMemo(() => {
    let filtered = users;
    
    // Apply search filter
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase().trim();
      filtered = filtered.filter(user => {
        // Search by username/global name
        if (user.username?.toLowerCase().includes(query)) {
          return true;
        }
        if (user.global_name?.toLowerCase().includes(query)) {
          return true;
        }
        // Search by RSI handle
        if (user.rsi_handle?.toLowerCase().includes(query)) {
          return true;
        }
        // Search by Discord ID (UUID)
        if (user.discord_id?.toLowerCase().includes(query)) {
          return true;
        }
        return false;
      });
    }
    
    // Apply org filter (AND logic - user must be in ALL selected orgs)
    if (selectedOrgs.length > 0) {
      filtered = filtered.filter(user => {
        const userOrgs = [
          ...(user.main_orgs || []),
          ...(user.affiliate_orgs || [])
        ];
        // Check if user has ALL selected orgs
        return selectedOrgs.every(org => userOrgs.includes(org));
      });
    }
    
    return filtered;
  }, [users, searchQuery, selectedOrgs]);
  
  // Export state
  const [exporting, setExporting] = useState(false);

  // Close org dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (orgDropdownOpen) {
        const target = event.target as HTMLElement;
        if (!target.closest('.org-dropdown-container')) {
          setOrgDropdownOpen(false);
        }
      }
    };
    
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [orgDropdownOpen]);

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
  const fetchUsers = async () => {
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
        normalizedStatusFilters.length > 0 ? normalizedStatusFilters : null
      );
      setUsers(data.items);
      setTotal(data.total);
      setTotalPages(data.total_pages);
      setIsCrossGuild(data.is_cross_guild === true);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load users');
    } finally {
      setLoading(false);
    }
  };

  // Load users on mount and when filters/pagination change
  useEffect(() => {
    fetchUsers();
  }, [page, pageSize, normalizedStatusFilters, activeGuildId]);

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

  // Get status badge variant
  const getStatusVariant = (status: string | null): 'success' | 'info' | 'warning' | 'neutral' => {
    switch (status) {
      case 'main':
        return 'success';
      case 'affiliate':
        return 'info';
      case 'non_member':
        return 'warning';
      default:
        return 'neutral';
    }
  };

  const formatDateValue = (value: string | number | null | undefined) => {
    if (!value) {
      return '-';
    }

    try {
      const date = typeof value === 'number' ? new Date(value * 1000) : new Date(value);
      if (Number.isNaN(date.getTime())) {
        return '-';
      }
      return date.toLocaleDateString();
    } catch (err) {
      return '-';
    }
  };

  const buildExportFilters = (): ExportUsersRequest => {
    const payload: ExportUsersRequest = {};

    if (normalizedStatusFilters.length === 1) {
      payload.membership_status = normalizedStatusFilters[0];
    }
    if (normalizedStatusFilters.length > 0) {
      payload.membership_statuses = normalizedStatusFilters;
    }

    return payload;
  };

  const startRecord = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const endRecord = total === 0 ? 0 : Math.min(page * pageSize, total);
  const totalPagesDisplay = totalPages > 0 ? totalPages : 1;

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
          <div className="flex-1 min-w-[250px]">
            <label className="block text-sm font-medium text-gray-400 mb-2">
              Membership Status
            </label>
            <div className="bg-slate-900 border border-slate-600 rounded px-4 py-2">
              {['main', 'affiliate', 'non_member', 'unknown'].map(status => (
                <label key={status} className="flex items-center py-1 cursor-pointer hover:bg-slate-800 px-2 rounded">
                  <input
                    type="checkbox"
                    checked={selectedStatuses.includes(status)}
                    onChange={() => toggleStatus(status)}
                    className="mr-2 h-4 w-4 text-indigo-600 focus:ring-indigo-500 border-gray-300 rounded"
                  />
                  <span className="text-white capitalize">{status.replace('_', ' ')}</span>
                </label>
              ))}
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

          {/* Apply Filters Button */}
          <div className="flex items-end">
            <Button
              onClick={fetchUsers}
              loading={loading}
            >
              {loading ? 'Loading...' : 'Apply Filters'}
            </Button>
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
                    <th className="px-4 py-3 text-left">
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
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase">
                      Guild
                    </th>
                  )}
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase">
                    User
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase">
                    Status
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase">
                    RSI Handle
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase">
                    Main Org
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase">
                    Affiliates
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase">
                    Roles
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase">
                    Joined Server
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase">
                    Account Created
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase">
                    Last Verified
                  </th>
                  {/* Hide actions column in cross-guild mode */}
                  {!isCrossGuild && (
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase">
                      Actions
                    </th>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700">
                {filteredUsers.map((user) => {
                  const isRowSelected = selectAllFiltered
                    ? !excludedIds.has(user.discord_id)
                    : selectedIds.has(user.discord_id);

                  return (
                    <tr key={user.discord_id} className="hover:bg-slate-700/50">
                    {/* Hide checkbox in cross-guild mode */}
                    {!isCrossGuild && (
                      <td className="px-4 py-4">
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
                      <td className="px-4 py-4">
                        <Badge variant="purple" className="text-xs">
                          {user.guild_name || user.guild_id || 'Unknown'}
                        </Badge>
                      </td>
                    )}
                    <td className="px-4 py-4">
                      <div className="flex items-center gap-3">
                        {user.avatar_url ? (
                          <img
                            src={user.avatar_url}
                            alt={user.username}
                            className="w-10 h-10 rounded-full"
                          />
                        ) : (
                          <div className="w-10 h-10 rounded-full bg-slate-700 flex items-center justify-center text-gray-400 font-bold">
                            {user.username.charAt(0).toUpperCase()}
                          </div>
                        )}
                        <div>
                          <div className="font-medium text-white">
                            {user.global_name || user.username}
                          </div>
                          <div className="text-sm text-gray-400">
                            {user.username}#{user.discriminator}
                          </div>
                          <div className="text-xs text-gray-500 font-mono mt-0.5">
                            {user.discord_id}
                          </div>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-4">
                      <Badge variant={getStatusVariant(user.membership_status)}>
                        {user.membership_status || 'unknown'}
                      </Badge>
                    </td>
                    <td className="px-4 py-4 text-sm text-gray-300">
                      {user.rsi_handle ? (
                        <a
                          href={`https://robertsspaceindustries.com/citizens/${user.rsi_handle}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-400 hover:text-blue-300 hover:underline"
                        >
                          {user.rsi_handle}
                        </a>
                      ) : (
                        '-'
                      )}
                    </td>
                    <td className="px-4 py-4 text-sm text-gray-300">
                      {user.main_orgs && user.main_orgs.length > 0 ? (
                        <div className="flex flex-wrap gap-1">
                          {user.main_orgs.filter(org => org !== 'REDACTED').map((org, idx) => (
                            <a
                              key={idx}
                              href={`https://robertsspaceindustries.com/orgs/${org}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="px-2 py-0.5 text-xs rounded bg-blue-900/30 text-blue-300 border border-blue-700/50 hover:bg-blue-900/50 hover:border-blue-600/70 transition-colors cursor-pointer"
                            >
                              {org}
                            </a>
                          ))}
                          {user.main_orgs.filter(org => org === 'REDACTED').length > 0 && (
                            <span className="px-2 py-0.5 text-xs rounded bg-slate-700 text-gray-400" title="Redacted organizations">
                              +{user.main_orgs.filter(org => org === 'REDACTED').length} redacted
                            </span>
                          )}
                        </div>
                      ) : (
                        <span className="text-gray-500">-</span>
                      )}
                    </td>
                    <td className="px-4 py-4 text-sm text-gray-300">
                      {user.affiliate_orgs && user.affiliate_orgs.length > 0 ? (
                        <div className="flex flex-wrap gap-1 max-w-xs">
                          {user.affiliate_orgs.filter(org => org !== 'REDACTED').slice(0, 3).map((org, idx) => (
                            <a
                              key={idx}
                              href={`https://robertsspaceindustries.com/orgs/${org}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="px-2 py-0.5 text-xs rounded bg-green-900/30 text-green-300 border border-green-700/50 hover:bg-green-900/50 hover:border-green-600/70 transition-colors cursor-pointer"
                            >
                              {org}
                            </a>
                          ))}
                          {user.affiliate_orgs.filter(org => org !== 'REDACTED').length > 3 && (
                            <span className="px-2 py-0.5 text-xs rounded bg-slate-700 text-gray-400" title={`${user.affiliate_orgs.filter(org => org !== 'REDACTED').slice(3).join(', ')}`}>
                              +{user.affiliate_orgs.filter(org => org !== 'REDACTED').length - 3}
                            </span>
                          )}
                          {user.affiliate_orgs.filter(org => org === 'REDACTED').length > 0 && (
                            <span className="px-2 py-0.5 text-xs rounded bg-slate-700 text-gray-400" title="Redacted organizations">
                              +{user.affiliate_orgs.filter(org => org === 'REDACTED').length} redacted
                            </span>
                          )}
                        </div>
                      ) : (
                        <span className="text-gray-500">-</span>
                      )}
                    </td>
                    <td className="px-4 py-4 text-sm">
                      <div className="flex flex-wrap gap-1 max-w-xs">
                        {user.roles.length > 0 ? (
                          user.roles.slice(0, 3).map((role) => (
                            <span
                              key={role.id}
                              className="px-2 py-1 text-xs rounded bg-slate-700 text-gray-300"
                              title={role.name}
                            >
                              {role.name}
                            </span>
                          ))
                        ) : (
                          <span className="text-gray-500">No roles</span>
                        )}
                        {user.roles.length > 3 && (
                          <span 
                            className="px-2 py-1 text-xs rounded bg-slate-700 text-gray-400 cursor-help"
                            title={user.roles.slice(3).map(r => r.name).join(', ')}
                          >
                            +{user.roles.length - 3}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-4 text-sm text-gray-400">
                      {formatDateValue(user.joined_at)}
                    </td>
                    <td className="px-4 py-4 text-sm text-gray-400">
                      {formatDateValue(user.created_at)}
                    </td>
                    <td className="px-4 py-4 text-sm text-gray-400">
                      {formatDateValue(user.last_updated)}
                    </td>
                    {/* Hide actions in cross-guild mode */}
                    {!isCrossGuild && (
                      <td className="px-4 py-4">
                        {canRecheck ? (
                          <Button
                            size="sm"
                            onClick={() => handleRecheckUser(user.discord_id)}
                            loading={recheckingUserId === user.discord_id}
                            title="Re-verify this user's RSI membership and update roles"
                          >
                            {recheckingUserId === user.discord_id ? 'Rechecking...' : 'Recheck'}
                          </Button>
                        ) : (
                          <span className="text-xs text-gray-500">-</span>
                        )}
                      </td>
                    )}
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="px-6 py-4 bg-slate-900 flex items-center justify-between border-t border-slate-700">
            <div className="text-sm text-gray-400">
              {total === 0 ? (
                'No results to display'
              ) : (
                <>
                  Showing {startRecord} to {endRecord} of {total} results
                </>
              )}
            </div>
            <div className="flex gap-2">
              <Button
                variant="secondary"
                onClick={handlePrevPage}
                disabled={page === 1}
              >
                Previous
              </Button>
              <div className="px-4 py-2 bg-slate-700 rounded">
                Page {page} of {totalPagesDisplay}
              </div>
              <Button
                variant="secondary"
                onClick={handleNextPage}
                disabled={page >= totalPages || total === 0}
              >
                Next
              </Button>
            </div>
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
