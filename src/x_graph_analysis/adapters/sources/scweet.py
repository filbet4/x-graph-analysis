"""Map raw Scweet records to the domain model."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from x_graph_analysis.domain.models import (
    Hashtag,
    Mention,
    Metrics,
    Post,
    User,
)


class ScweetPostMapper:
    """Map Scweet Search and raw tweet records to domain posts."""

    def map_seed(self, item: dict[str, Any]) -> Post:
        """Map a Search seed wrapper to a domain post."""
        record = item.get("record")

        if not isinstance(record, dict):
            raise ValueError("Seed item does not contain a valid record.")

        raw = record.get("raw")

        if not isinstance(raw, dict):
            raise ValueError("Seed record does not contain raw tweet data.")

        post_id = item.get("tweet_id") or record.get("tweet_id")

        if not post_id:
            raise ValueError("Seed post does not contain a tweet ID.")

        return self._map_raw(
            raw=raw,
            post_id=str(post_id),
            fallback_record=record,
        )

    def map_target(self, record: dict[str, Any]) -> Post:
        """Map a raw one-hop target record to a domain post."""
        post_id = record.get("rest_id")

        if not post_id:
            legacy = record.get("legacy")

            if isinstance(legacy, dict):
                post_id = legacy.get("id_str")

        if not post_id:
            raise ValueError("Target record does not contain a tweet ID.")

        return self._map_raw(
            raw=record,
            post_id=str(post_id),
        )

    def _map_raw(
        self,
        raw: dict[str, Any],
        post_id: str,
        fallback_record: dict[str, Any] | None = None,
    ) -> Post:
        """Map common raw X data to a domain post."""
        raw = self._unwrap_tweet(raw)

        legacy = raw.get("legacy")

        if not isinstance(legacy, dict):
            legacy = {}

        author = self._map_author(raw, fallback_record)

        text = legacy.get("full_text")

        if not text and fallback_record is not None:
            text = fallback_record.get("text")

        created_at = legacy.get("created_at")

        if not created_at and fallback_record is not None:
            created_at = (
                fallback_record.get("timestamp")
                or fallback_record.get("created_at")
            )

        return Post(
            post_id=post_id,
            author=author,
            text=str(text or ""),
            published_at=self._parse_datetime(created_at),
            hashtags=self._map_hashtags(legacy, fallback_record),
            mentions=self._map_mentions(legacy),
            metrics=self._map_metrics(raw, legacy, fallback_record),
            reply_to_post_id=self._optional_string(
                legacy.get("in_reply_to_status_id_str")
            ),
            quoted_post_id=self._optional_string(
                legacy.get("quoted_status_id_str")
            ),
            reposted_post_id=self._get_repost_target(
                legacy,
                fallback_record,
            ),
        )

    @staticmethod
    def _unwrap_tweet(raw: dict[str, Any]) -> dict[str, Any]:
        """Unwrap visibility-limited tweet results."""
        if raw.get("__typename") == "TweetWithVisibilityResults":
            tweet = raw.get("tweet")

            if isinstance(tweet, dict):
                return tweet

        return raw
    
    def _map_author(
        self,
        raw: dict[str, Any],
        fallback_record: dict[str, Any] | None,
    ) -> User:
        """Map tweet author data."""
        core = raw.get("core")
        user_result: dict[str, Any] = {}

        if isinstance(core, dict):
            user_results = core.get("user_results")

            if isinstance(user_results, dict):
                result = user_results.get("result")

                if isinstance(result, dict):
                    user_result = result

        user_core = user_result.get("core")

        if not isinstance(user_core, dict):
            user_core = {}

        fallback_user: dict[str, Any] = {}

        if fallback_record is not None:
            value = fallback_record.get("user")

            if isinstance(value, dict):
                fallback_user = value

        user_id = (
            user_result.get("rest_id")
            or self._legacy_user_id(raw)
            or (
                fallback_record.get("user_id")
                if fallback_record is not None
                else None
            )
        )

        if not user_id:
            raise ValueError("Tweet author does not contain a user ID.")

        username = (
            user_core.get("screen_name")
            or fallback_user.get("screen_name")
            or ""
        )

        display_name = (
            user_core.get("name")
            or fallback_user.get("name")
        )

        verification = user_result.get("verification")
        verified = False

        if isinstance(verification, dict):
            verified = bool(verification.get("verified"))

        verified = verified or bool(
            user_result.get("is_blue_verified")
        )

        return User(
            user_id=str(user_id),
            username=str(username),
            display_name=(
                str(display_name)
                if display_name is not None
                else None
            ),
            verified=verified,
        )

    @staticmethod
    def _legacy_user_id(raw: dict[str, Any]) -> str | None:
        legacy = raw.get("legacy")

        if not isinstance(legacy, dict):
            return None

        value = legacy.get("user_id_str")

        return str(value) if value else None

    @staticmethod
    def _map_hashtags(
        legacy: dict[str, Any],
        fallback_record: dict[str, Any] | None,
    ) -> tuple[Hashtag, ...]:
        values: list[Any] = []

        entities = legacy.get("entities")

        if isinstance(entities, dict):
            raw_hashtags = entities.get("hashtags")

            if isinstance(raw_hashtags, list):
                values.extend(raw_hashtags)

        if not values and fallback_record is not None:
            fallback = fallback_record.get("hashtags")

            if isinstance(fallback, list):
                values.extend(fallback)

        hashtags: dict[str, Hashtag] = {}

        for value in values:
            if isinstance(value, dict):
                text = (
                    value.get("text")
                    or value.get("tag")
                    or value.get("name")
                )
            else:
                text = value

            if not text:
                continue

            clean_text = str(text).strip().lstrip("#")

            if not clean_text:
                continue

            normalized = clean_text.lower()

            hashtags[normalized] = Hashtag(
                text=clean_text,
                normalized_text=normalized,
            )

        return tuple(hashtags.values())

    @staticmethod
    def _map_mentions(
        legacy: dict[str, Any],
    ) -> tuple[Mention, ...]:
        """Map user mentions contained in a tweet."""
        entities = legacy.get("entities")

        if not isinstance(entities, dict):
            return ()

        values = entities.get("user_mentions")

        if not isinstance(values, list):
            return ()

        mentions: list[Mention] = []

        for value in values:
            if not isinstance(value, dict):
                continue

            user_id = value.get("id_str")
            username = value.get("screen_name")

            if not user_id or not username:
                continue

            display_name = value.get("name")

            user = User(
                user_id=str(user_id),
                username=str(username),
                display_name=(
                    str(display_name)
                    if display_name is not None
                    else None
                ),
            )

            mentions.append(
                Mention(
                    user=user,
                    username=str(username),
                )
            )

        return tuple(mentions)


    @staticmethod
    def _map_metrics(
        raw: dict[str, Any],
        legacy: dict[str, Any],
        fallback_record: dict[str, Any] | None,
    ) -> Metrics:
        views = raw.get("views")
        view_count = 0

        if isinstance(views, dict):
            value = views.get("count")

            if value is not None:
                try:
                    view_count = int(value)
                except (TypeError, ValueError):
                    view_count = 0

        if view_count == 0 and fallback_record is not None:
            try:
                view_count = int(fallback_record.get("views") or 0)
            except (TypeError, ValueError):
                view_count = 0

        return Metrics(
            like_count=int(legacy.get("favorite_count") or 0),
            repost_count=int(legacy.get("retweet_count") or 0),
            reply_count=int(legacy.get("reply_count") or 0),
            quote_count=int(legacy.get("quote_count") or 0),
            view_count=view_count,
        )

    @staticmethod
    def _get_repost_target(
        legacy: dict[str, Any],
        fallback_record: dict[str, Any] | None,
    ) -> str | None:
        if fallback_record is not None:
            retweeted_tweet = fallback_record.get("retweeted_tweet")

            if isinstance(retweeted_tweet, dict):
                value = (
                    retweeted_tweet.get("tweet_id")
                    or retweeted_tweet.get("id")
                    or retweeted_tweet.get("id_str")
                )

                if value:
                    return str(value)

        retweeted_status = legacy.get("retweeted_status_result")

        if isinstance(retweeted_status, dict):
            result = retweeted_status.get("result")

            if isinstance(result, dict):
                value = result.get("rest_id") or result.get("id_str")

                if value:
                    return str(value)

        return None

    @staticmethod
    def _parse_datetime(value: Any) -> datetime:
        if not value:
            raise ValueError("Tweet does not contain a creation timestamp.")

        text = str(value)

        formats = (
            "%a %b %d %H:%M:%S %z %Y",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S%z",
        )

        for date_format in formats:
            try:
                return datetime.strptime(text, date_format)
            except ValueError:
                continue

        raise ValueError(f"Unsupported tweet timestamp: {text}")

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        if value is None:
            return None

        text = str(value)

        return text if text else None