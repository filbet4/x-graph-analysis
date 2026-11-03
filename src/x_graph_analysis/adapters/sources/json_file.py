"""JSON file adapter for loading source records into domain entities.

TODO: Add schema versioning and provenance metadata when the ingestion contract
is formalized.
"""

import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from x_graph_analysis.domain.models import (
    Hashtag,
    Mention,
    Metrics,
    Post,
    PostCollection,
    User,
)
from x_graph_analysis.domain.ports import PostSource


class JsonDataSourceError(ValueError):
    """Raised when a local JSON file cannot be mapped to domain entities."""


class LocalJsonPostSource(PostSource):
    """Load a collection of posts from a local JSON array."""

    def __init__(self, file_path: Path, source_name: str = "local-json") -> None:
        self._file_path = file_path
        self._source_name = source_name

    @property
    def name(self) -> str:
        """Return the stable name of this data source."""
        return self._source_name

    def collect(self) -> PostCollection:
        """Read the file and map every JSON record into a domain post."""
        try:
            with self._file_path.open(encoding="utf-8") as input_file:
                raw_records: object = json.load(input_file)
        except (OSError, json.JSONDecodeError) as error:
            raise JsonDataSourceError(
                f"Unable to read valid JSON from {self._file_path}"
            ) from error

        if not isinstance(raw_records, list):
            raise JsonDataSourceError("The JSON root must be an array of post records")

        try:
            posts = tuple(
                self._map_post(record, index)
                for index, record in enumerate(raw_records)
            )
        except (TypeError, ValueError, KeyError) as error:
            raise JsonDataSourceError(f"Invalid post record: {error}") from error

        return PostCollection(
            posts=posts,
            source_name=self.name,
            collected_at=datetime.now().astimezone(),
        )

    @classmethod
    def _map_post(cls, raw_record: object, index: int) -> Post:
        record = cls._mapping(raw_record, f"record {index}")
        return Post(
            post_id=cls._required_str(record, "post_id"),
            author=cls._map_user(record.get("author"), f"record {index}.author"),
            text=cls._required_str(record, "text"),
            published_at=cls._timestamp(record, "published_at"),
            hashtags=tuple(
                cls._map_hashtag(item, f"record {index}.hashtags[{item_index}]")
                for item_index, item in enumerate(
                    cls._list(record.get("hashtags", []), "hashtags")
                )
            ),
            mentions=tuple(
                cls._map_mention(item, f"record {index}.mentions[{item_index}]")
                for item_index, item in enumerate(
                    cls._list(record.get("mentions", []), "mentions")
                )
            ),
            metrics=cls._map_metrics(record.get("metrics"), f"record {index}.metrics"),
            reply_to_post_id=cls._optional_str(record, "reply_to_post_id"),
            quoted_post_id=cls._optional_str(record, "quoted_post_id"),
            reposted_post_id=cls._optional_str(record, "reposted_post_id"),
        )

    @classmethod
    def _map_user(cls, raw_user: object, context: str) -> User:
        user = cls._mapping(raw_user, context)
        return User(
            user_id=cls._required_str(user, "user_id", context),
            username=cls._required_str(user, "username", context),
            display_name=cls._optional_str(user, "display_name"),
            verified=cls._optional_bool(user, "verified", False),
        )

    @classmethod
    def _map_hashtag(cls, raw_hashtag: object, context: str) -> Hashtag:
        hashtag = cls._mapping(raw_hashtag, context)
        text = cls._required_str(hashtag, "text", context)
        return Hashtag(
            text=text,
            normalized_text=cls._optional_str(hashtag, "normalized_text")
            or text.casefold(),
        )

    @classmethod
    def _map_mention(cls, raw_mention: object, context: str) -> Mention:
        mention = cls._mapping(raw_mention, context)
        return Mention(
            user=cls._map_user(mention.get("user"), f"{context}.user"),
            username=cls._required_str(mention, "username", context),
            start_offset=cls._optional_int(mention, "start_offset"),
            end_offset=cls._optional_int(mention, "end_offset"),
        )

    @classmethod
    def _map_metrics(cls, raw_metrics: object, context: str) -> Metrics | None:
        if raw_metrics is None:
            return None
        metrics = cls._mapping(raw_metrics, context)
        return Metrics(
            like_count=cls._optional_int(metrics, "like_count") or 0,
            repost_count=cls._optional_int(metrics, "repost_count") or 0,
            reply_count=cls._optional_int(metrics, "reply_count") or 0,
            quote_count=cls._optional_int(metrics, "quote_count") or 0,
            view_count=cls._optional_int(metrics, "view_count"),
        )

    @staticmethod
    def _mapping(value: object, context: str) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise TypeError(f"{context} must be an object")
        return value

    @staticmethod
    def _list(value: object, field_name: str) -> list[object]:
        if not isinstance(value, list):
            raise TypeError(f"{field_name} must be an array")
        return value

    @staticmethod
    def _required_str(
        record: Mapping[str, Any], field_name: str, context: str = "record"
    ) -> str:
        value = record.get(field_name)
        if not isinstance(value, str) or not value:
            raise ValueError(f"{context}.{field_name} must be a non-empty string")
        return value

    @staticmethod
    def _optional_str(record: Mapping[str, Any], field_name: str) -> str | None:
        value = record.get(field_name)
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError(f"{field_name} must be a string or null")
        return value

    @staticmethod
    def _optional_bool(
        record: Mapping[str, Any], field_name: str, default: bool
    ) -> bool:
        value = record.get(field_name, default)
        if not isinstance(value, bool):
            raise TypeError(f"{field_name} must be a boolean")
        return value

    @staticmethod
    def _optional_int(record: Mapping[str, Any], field_name: str) -> int | None:
        value = record.get(field_name)
        if value is None:
            return None
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError(f"{field_name} must be an integer or null")
        return value

    @staticmethod
    def _timestamp(record: Mapping[str, Any], field_name: str) -> datetime:
        value = LocalJsonPostSource._required_str(record, field_name)
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError(f"{field_name} must be an ISO 8601 timestamp") from error
