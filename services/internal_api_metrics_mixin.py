"""Metrics and activity group route handlers for InternalAPIServer."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aiohttp import web

from services.db.repository import BaseRepository
from utils.logging import get_logger

if TYPE_CHECKING:
    from bot import MyBot
    from services.service_container import ServiceContainer

logger = get_logger(__name__)


class InternalAPIMetricsMixin:
    """Mixin providing metrics and activity group HTTP handlers.

    Requires the host class to provide:
    - self.services — ServiceContainer
    - self.bot — MyBot or None
    - self._check_auth(request) — returns bool
    """

    if TYPE_CHECKING:
        services: ServiceContainer
        bot: MyBot | None

    def _check_auth(self, request: web.Request) -> bool:
        """Host class must provide auth check implementation."""
        raise NotImplementedError

    def _get_metrics_service(self):
        """Get the metrics service, returning None if unavailable."""
        try:
            return self.services.metrics
        except (AttributeError, RuntimeError):
            return None

    @staticmethod
    def _parse_user_ids(request: web.Request) -> list[int] | None:
        """Parse optional user_ids query param (comma-separated).

        Returns None when the parameter is absent, or a list of ints when
        present and valid.  Raises a 400 error if the value is present but
        contains non-numeric entries so callers can detect and correct bad IDs
        instead of unexpectedly receiving unfiltered metrics.
        """
        raw = request.query.get("user_ids")
        if not raw:
            return None
        try:
            ids = [int(uid.strip()) for uid in raw.split(",") if uid.strip()]
        except (TypeError, ValueError):
            raise web.HTTPBadRequest(
                text='{"error": "Invalid user_ids parameter — expected comma-separated integers"}',
                content_type="application/json",
            )
        if not ids:
            return None
        return ids

    async def _enrich_leaderboard_entries(
        self,
        guild_id: int,
        entries: list[dict],
    ) -> None:
        """Best-effort enrichment of leaderboard entries with Discord profiles.

        Mutates *entries* in-place — adds ``username`` and ``avatar_url``
        resolved from the guild member cache, a ``fetch_member`` fallback, or
        the verification DB.

        AI Notes:
            Extracted from the voice and message leaderboard handlers so both
            endpoints stay behaviorally consistent when updated.
        """
        guild = self.bot.get_guild(guild_id) if self.bot else None
        for entry in entries:
            raw_user_id = entry.get("user_id")
            if raw_user_id is None:
                continue
            try:
                user_id = int(raw_user_id)
            except (TypeError, ValueError):
                continue

            member = guild.get_member(user_id) if guild else None
            if member is None and guild is not None:
                try:
                    member = await guild.fetch_member(user_id)
                except Exception:
                    member = None

            if member is not None:
                entry["username"] = member.display_name
                try:
                    entry["avatar_url"] = str(member.display_avatar.url)
                except Exception:
                    entry["avatar_url"] = None
                continue

            # DB fallback if member can't be resolved from guild
            try:
                row = await BaseRepository.fetch_one(
                    "SELECT community_moniker, rsi_handle FROM verification WHERE user_id = ?",
                    (user_id,),
                )
                if row:
                    entry["username"] = row[0] or row[1] or entry.get("username")
            except Exception:
                logger.debug("DB fallback for leaderboard entry user_id=%s failed", raw_user_id)

    async def get_metrics_overview(self, request: web.Request) -> web.Response:
        """
        Get metrics overview for a guild: live snapshot + aggregated period data.

        Path: GET /guilds/{guild_id}/metrics/overview
        Query params: days (int, default 7)

        Returns: {
            "live": { messages_today, active_voice_users, active_game_sessions, top_game },
            "period": { total_messages, avg_messages_per_user, total_voice_seconds, ... }
        }
        """
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)

        metrics = self._get_metrics_service()
        if metrics is None:
            return web.json_response(
                {"error": "Metrics service unavailable"}, status=503
            )

        try:
            guild_id = int(request.match_info["guild_id"])
        except (KeyError, ValueError):
            return web.json_response({"error": "Invalid guild ID"}, status=400)

        try:
            days = int(request.query.get("days", "7"))
        except (TypeError, ValueError):
            return web.json_response({"error": "Invalid days parameter"}, status=400)
        days = max(1, min(days, 365))

        try:
            live = metrics.get_live_snapshot(guild_id)
            messages_today = await metrics.get_messages_today(guild_id)
            user_ids = self._parse_user_ids(request)
            period = await metrics.get_guild_metrics(
                guild_id, days=days, user_ids=user_ids
            )

            return web.json_response(
                {
                    "live": {
                        "messages_today": messages_today,
                        "active_voice_users": live.active_voice_users,
                        "active_game_sessions": live.active_game_sessions,
                        "top_game": live.top_game,
                    },
                    "period": period,
                }
            )
        except Exception:
            logger.exception("Error fetching metrics overview")
            return web.json_response({"error": "Failed to fetch metrics"}, status=500)

    async def get_metrics_voice_leaderboard(self, request: web.Request) -> web.Response:
        """
        Get top users by voice time.

        Path: GET /guilds/{guild_id}/metrics/voice/leaderboard
        Query params: days (int, default 7), limit (int, default 10)
        """
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)

        metrics = self._get_metrics_service()
        if metrics is None:
            return web.json_response(
                {"error": "Metrics service unavailable"}, status=503
            )

        try:
            guild_id = int(request.match_info["guild_id"])
        except (KeyError, ValueError):
            return web.json_response({"error": "Invalid guild ID"}, status=400)

        try:
            days = int(request.query.get("days", "7"))
        except (TypeError, ValueError):
            return web.json_response({"error": "Invalid days parameter"}, status=400)
        days = max(1, min(days, 365))
        try:
            limit = int(request.query.get("limit", "10"))
        except (TypeError, ValueError):
            return web.json_response({"error": "Invalid limit parameter"}, status=400)
        limit = max(1, min(limit, 50))

        try:
            leaderboard = await metrics.get_voice_leaderboard(
                guild_id,
                days=days,
                limit=limit,
                user_ids=self._parse_user_ids(request),
            )

            await self._enrich_leaderboard_entries(guild_id, leaderboard)

            return web.json_response({"entries": leaderboard})
        except Exception:
            logger.exception("Error fetching voice leaderboard")
            return web.json_response(
                {"error": "Failed to fetch voice leaderboard"}, status=500
            )

    async def get_metrics_message_leaderboard(
        self, request: web.Request
    ) -> web.Response:
        """
        Get top users by message count.

        Path: GET /guilds/{guild_id}/metrics/messages/leaderboard
        Query params: days (int, default 7), limit (int, default 10)
        """
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)

        metrics = self._get_metrics_service()
        if metrics is None:
            return web.json_response(
                {"error": "Metrics service unavailable"}, status=503
            )

        try:
            guild_id = int(request.match_info["guild_id"])
        except (KeyError, ValueError):
            return web.json_response({"error": "Invalid guild ID"}, status=400)

        try:
            days = int(request.query.get("days", "7"))
        except (TypeError, ValueError):
            return web.json_response({"error": "Invalid days parameter"}, status=400)
        days = max(1, min(days, 365))
        try:
            limit = int(request.query.get("limit", "10"))
        except (TypeError, ValueError):
            return web.json_response({"error": "Invalid limit parameter"}, status=400)
        limit = max(1, min(limit, 50))

        try:
            leaderboard = await metrics.get_message_leaderboard(
                guild_id,
                days=days,
                limit=limit,
                user_ids=self._parse_user_ids(request),
            )

            await self._enrich_leaderboard_entries(guild_id, leaderboard)

            return web.json_response({"entries": leaderboard})
        except Exception:
            logger.exception("Error fetching message leaderboard")
            return web.json_response(
                {"error": "Failed to fetch message leaderboard"}, status=500
            )

    async def get_metrics_top_games(self, request: web.Request) -> web.Response:
        """
        Get top games by total play time.

        Path: GET /guilds/{guild_id}/metrics/games/top
        Query params: days (int, default 7), limit (int, default 10)
        """
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)

        metrics = self._get_metrics_service()
        if metrics is None:
            return web.json_response(
                {"error": "Metrics service unavailable"}, status=503
            )

        try:
            guild_id = int(request.match_info["guild_id"])
        except (KeyError, ValueError):
            return web.json_response({"error": "Invalid guild ID"}, status=400)

        try:
            days = int(request.query.get("days", "7"))
        except (TypeError, ValueError):
            return web.json_response({"error": "Invalid days parameter"}, status=400)
        days = max(1, min(days, 365))
        try:
            limit = int(request.query.get("limit", "10"))
        except (TypeError, ValueError):
            return web.json_response({"error": "Invalid limit parameter"}, status=400)
        limit = max(1, min(limit, 50))

        try:
            games = await metrics.get_top_games(
                guild_id,
                days=days,
                limit=limit,
                user_ids=self._parse_user_ids(request),
            )
            return web.json_response({"games": games})
        except Exception:
            logger.exception("Error fetching top games")
            return web.json_response({"error": "Failed to fetch top games"}, status=500)

    async def get_metrics_game(self, request: web.Request) -> web.Response:
        """
        Get detailed metrics for a specific game.

        Path: GET /guilds/{guild_id}/metrics/games/detail
        Query params: game_name (required), days (int, default 7), limit (int, default 5)
        """
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)

        metrics = self._get_metrics_service()
        if metrics is None:
            return web.json_response(
                {"error": "Metrics service unavailable"}, status=503
            )

        try:
            guild_id = int(request.match_info["guild_id"])
        except (KeyError, ValueError):
            return web.json_response({"error": "Invalid guild ID"}, status=400)

        game_name = str(request.query.get("game_name", "")).strip()
        if not game_name:
            return web.json_response({"error": "Missing game_name parameter"}, status=400)

        try:
            days = int(request.query.get("days", "7"))
        except (TypeError, ValueError):
            return web.json_response({"error": "Invalid days parameter"}, status=400)
        days = max(1, min(days, 365))

        try:
            limit = int(request.query.get("limit", "5"))
        except (TypeError, ValueError):
            return web.json_response({"error": "Invalid limit parameter"}, status=400)
        limit = max(1, min(limit, 20))

        try:
            data = await metrics.get_game_metrics(
                guild_id,
                game_name=game_name,
                days=days,
                limit=limit,
                user_ids=self._parse_user_ids(request),
            )
            top_players = data.get("top_players", [])
            if isinstance(top_players, list):
                await self._enrich_leaderboard_entries(guild_id, top_players)
            return web.json_response(data)
        except web.HTTPBadRequest:
            raise
        except Exception:
            logger.exception("Error fetching game metrics")
            return web.json_response(
                {"error": "Failed to fetch game metrics"},
                status=500,
            )

    async def get_metrics_timeseries(self, request: web.Request) -> web.Response:
        """
        Get hourly time-series data for charts.

        Path: GET /guilds/{guild_id}/metrics/timeseries
        Query params: metric (messages|voice|games, default messages), days (int, default 7)
        """
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)

        metrics = self._get_metrics_service()
        if metrics is None:
            return web.json_response(
                {"error": "Metrics service unavailable"}, status=503
            )

        try:
            guild_id = int(request.match_info["guild_id"])
        except (KeyError, ValueError):
            return web.json_response({"error": "Invalid guild ID"}, status=400)

        metric = request.query.get("metric", "messages")
        if metric not in ("messages", "voice", "games"):
            return web.json_response(
                {"error": f"Invalid metric: {metric}. Use messages, voice, or games"},
                status=400,
            )
        try:
            days = int(request.query.get("days", "7"))
        except (TypeError, ValueError):
            return web.json_response({"error": "Invalid days parameter"}, status=400)
        days = max(1, min(days, 365))

        try:
            data = await metrics.get_timeseries(
                guild_id,
                metric=metric,
                days=days,
                user_ids=self._parse_user_ids(request),
            )
            return web.json_response({"metric": metric, "days": days, "data": data})
        except Exception:
            logger.exception("Error fetching timeseries")
            return web.json_response(
                {"error": "Failed to fetch timeseries"}, status=500
            )

    async def get_metrics_user(self, request: web.Request) -> web.Response:
        """
        Get detailed metrics for a specific user.

        Path: GET /guilds/{guild_id}/metrics/user/{user_id}
        Query params: days (int, default 7)
        """
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)

        metrics = self._get_metrics_service()
        if metrics is None:
            return web.json_response(
                {"error": "Metrics service unavailable"}, status=503
            )

        try:
            guild_id = int(request.match_info["guild_id"])
            user_id = int(request.match_info["user_id"])
        except (KeyError, ValueError):
            return web.json_response({"error": "Invalid guild/user ID"}, status=400)

        try:
            days = int(request.query.get("days", "7"))
        except (TypeError, ValueError):
            return web.json_response({"error": "Invalid days parameter"}, status=400)
        days = max(1, min(days, 365))

        try:
            data = await metrics.get_user_metrics(guild_id, user_id, days=days)

            # Attach guild member display metadata (best-effort)
            try:
                guild = self.bot.get_guild(guild_id) if self.bot else None
                member = None
                if guild is not None:
                    member = guild.get_member(user_id)
                    if member is None:
                        try:
                            member = await guild.fetch_member(user_id)
                        except Exception:
                            member = None
                if member is not None:
                    data["username"] = member.display_name
                    data["avatar_url"] = str(member.display_avatar.url)
            except Exception:
                logger.warning(
                    "Failed to enrich metrics user with member profile for user_id=%d",
                    user_id,
                )

            # Attach per-dimension activity tiers
            try:
                buckets = await metrics.get_member_activity_buckets(
                    guild_id, user_ids=[user_id]
                )
                user_bucket = buckets.get(user_id, {})
                data["voice_tier"] = user_bucket.get("voice_tier")
                data["chat_tier"] = user_bucket.get("chat_tier")
                data["game_tier"] = user_bucket.get("game_tier")
                data["combined_tier"] = user_bucket.get("combined_tier")
                data["last_voice_at"] = user_bucket.get("last_voice_at")
                data["last_chat_at"] = user_bucket.get("last_chat_at")
                data["last_game_at"] = user_bucket.get("last_game_at")
            except Exception:
                logger.warning("Failed to compute activity tiers for user %d", user_id)

            return web.json_response(data)
        except Exception:
            logger.exception("Error fetching user metrics")
            return web.json_response(
                {"error": "Failed to fetch user metrics"}, status=500
            )

    async def get_activity_groups(self, request: web.Request) -> web.Response:
        """
        Get activity group tier counts per dimension.

        Path: GET /guilds/{guild_id}/metrics/activity-groups
        Returns: { voice: {hardcore: N, ...}, chat: {...}, game: {...}, combined: {...} }
        """
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)

        metrics = self._get_metrics_service()
        if metrics is None:
            return web.json_response(
                {"error": "Metrics service unavailable"}, status=503
            )

        try:
            guild_id = int(request.match_info["guild_id"])
        except (KeyError, ValueError):
            return web.json_response({"error": "Invalid guild ID"}, status=400)

        try:
            days = int(request.query.get("days", "7"))
        except (TypeError, ValueError):
            return web.json_response({"error": "Invalid days parameter"}, status=400)
        days = max(1, min(days, 365))

        try:
            user_ids = self._parse_user_ids(request)
        except web.HTTPBadRequest as exc:
            return web.json_response({"error": str(exc.reason)}, status=400)

        try:
            counts = await metrics.get_activity_group_counts(
                guild_id,
                user_ids=user_ids,
                days=days,
            )
            return web.json_response(counts)
        except Exception:
            logger.exception("Error fetching activity groups")
            return web.json_response(
                {"error": "Failed to fetch activity groups"}, status=500
            )

    async def get_activity_group_members(self, request: web.Request) -> web.Response:
        """
        Get user IDs belonging to a specific dimension+tier.

        Path: GET /guilds/{guild_id}/metrics/activity-group-members
        Query params: dimension (voice|chat|game|combined), tier (hardcore|regular|casual|reserve|inactive)
        Returns: { user_ids: [int, ...] }
        """
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)

        metrics = self._get_metrics_service()
        if metrics is None:
            return web.json_response(
                {"error": "Metrics service unavailable"}, status=503
            )

        try:
            guild_id = int(request.match_info["guild_id"])
        except (KeyError, ValueError):
            return web.json_response({"error": "Invalid guild ID"}, status=400)

        dimension = request.query.get("dimension", "combined")
        if dimension not in ("voice", "chat", "game", "combined"):
            return web.json_response(
                {
                    "error": f"Invalid dimension: {dimension}. Use voice, chat, game, or combined"
                },
                status=400,
            )
        tier = request.query.get("tier", "")
        if tier not in ("hardcore", "regular", "casual", "reserve", "inactive"):
            return web.json_response(
                {
                    "error": f"Invalid tier: {tier}. Use hardcore, regular, casual, reserve, or inactive"
                },
                status=400,
            )

        try:
            user_ids = await metrics.get_activity_group_user_ids(
                guild_id, dimension, tier
            )
            return web.json_response({"user_ids": user_ids})
        except Exception:
            logger.exception("Error fetching activity group members")
            return web.json_response(
                {"error": "Failed to fetch activity group members"}, status=500
            )

    async def get_activity_group_members_bulk(
        self, request: web.Request
    ) -> web.Response:
        """
        Get user IDs for multiple dimension+tier combos in a single call.

        Path: GET /guilds/{guild_id}/metrics/activity-group-members-bulk
        Query params:
            dimensions  – comma-separated (voice,chat,game,combined)
            tiers       – comma-separated (hardcore,regular,casual,reserve,inactive)
            days        – lookback period in days (default 30, 1–365)
        Returns: { "<dimension>": { "<tier>": [int, ...], ... }, ... }
        """
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)

        metrics = self._get_metrics_service()
        if metrics is None:
            return web.json_response(
                {"error": "Metrics service unavailable"}, status=503
            )

        try:
            guild_id = int(request.match_info["guild_id"])
        except (KeyError, ValueError):
            return web.json_response({"error": "Invalid guild ID"}, status=400)

        try:
            days = int(request.query.get("days", "30"))
        except (TypeError, ValueError):
            return web.json_response({"error": "Invalid days parameter"}, status=400)
        days = max(1, min(days, 365))

        valid_dims = {"voice", "chat", "game", "combined"}
        valid_tiers = {"hardcore", "regular", "casual", "reserve", "inactive"}

        raw_dims = request.query.get("dimensions", "")
        dimensions = [d.strip() for d in raw_dims.split(",") if d.strip()]
        if not dimensions or not all(d in valid_dims for d in dimensions):
            return web.json_response(
                {
                    "error": "Invalid or missing dimensions param. Use comma-separated: voice, chat, game, combined"
                },
                status=400,
            )

        raw_tiers = request.query.get("tiers", "")
        tiers = [t.strip() for t in raw_tiers.split(",") if t.strip()]
        if not tiers or not all(t in valid_tiers for t in tiers):
            return web.json_response(
                {
                    "error": "Invalid or missing tiers param. Use comma-separated: hardcore, regular, casual, reserve, inactive"
                },
                status=400,
            )

        try:
            result = await metrics.get_activity_group_user_ids_bulk(
                guild_id,
                dimensions,
                tiers,
                lookback_days=days,
            )
            return web.json_response(result)
        except Exception:
            logger.exception("Error fetching bulk activity group members")
            return web.json_response(
                {"error": "Failed to fetch bulk activity group members"},
                status=500,
            )

    async def delete_metrics_user(self, request: web.Request) -> web.Response:
        """
        Delete all metrics data for a specific user in a guild (data erasure).

        Path: DELETE /guilds/{guild_id}/metrics/user/{user_id}
        Headers: Authorization: Bearer <api_key>

        Returns: { "deleted": { table_name: row_count, ... } }
        """
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)

        metrics = self._get_metrics_service()
        if metrics is None:
            return web.json_response(
                {"error": "Metrics service unavailable"}, status=503
            )

        try:
            guild_id = int(request.match_info["guild_id"])
            user_id = int(request.match_info["user_id"])
        except (KeyError, ValueError):
            return web.json_response({"error": "Invalid guild/user ID"}, status=400)

        try:
            deleted = await metrics.delete_user_metrics(guild_id, user_id)
            return web.json_response({"deleted": deleted})
        except Exception:
            logger.exception("Error deleting user metrics")
            return web.json_response(
                {"error": "Failed to delete user metrics"}, status=500
            )
