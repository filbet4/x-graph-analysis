"""Tests for mapping Scweet records to the domain model."""

from x_graph_analysis.adapters.sources.scweet import ScweetPostMapper


def test_map_seed() -> None:
    """Map a normalized Scweet Search seed."""
    mapper = ScweetPostMapper()

    item = {
        "tweet_id": "100",
        "record": {
            "tweet_id": "100",
            "user": {
                "screen_name": "author",
                "name": "Author Name",
            },
            "timestamp": "Wed Oct 07 23:09:03 +0000 2026",
            "text": "@mentioned Example post #Test",
            "hashtags": ["Test"],
            "raw": {
                "core": {
                    "user_results": {
                        "result": {
                            "rest_id": "10",
                            "core": {
                                "screen_name": "author",
                                "name": "Author Name",
                            },
                            "verification": {
                                "verified": False,
                            },
                        }
                    }
                },
                "legacy": {
                    "created_at": "Wed Oct 07 23:09:03 +0000 2026",
                    "full_text": "@mentioned Example post #Test",
                    "favorite_count": 5,
                    "retweet_count": 2,
                    "reply_count": 3,
                    "quote_count": 1,
                    "in_reply_to_status_id_str": "99",
                    "entities": {
                        "hashtags": [
                            {"text": "Test"},
                        ],
                        "user_mentions": [
                            {
                                "id_str": "20",
                                "screen_name": "mentioned",
                                "name": "Mentioned User",
                            }
                        ],
                    },
                },
                "views": {
                    "count": "1000",
                },
            },
        },
    }

    post = mapper.map_seed(item)

    assert post.post_id == "100"
    assert post.author.user_id == "10"
    assert post.author.username == "author"
    assert post.author.display_name == "Author Name"

    assert post.text == "@mentioned Example post #Test"
    assert post.published_at.year == 2026

    assert post.reply_to_post_id == "99"
    assert post.quoted_post_id is None
    assert post.reposted_post_id is None

    assert len(post.hashtags) == 1
    assert post.hashtags[0].normalized_text == "test"

    assert len(post.mentions) == 1
    assert post.mentions[0].username == "mentioned"
    assert post.mentions[0].user.user_id == "20"

    assert post.metrics.like_count == 5
    assert post.metrics.repost_count == 2
    assert post.metrics.reply_count == 3
    assert post.metrics.quote_count == 1
    assert post.metrics.view_count == 1000


def test_map_one_hop_target() -> None:
    """Map a raw Scweet one-hop target."""
    mapper = ScweetPostMapper()

    record = {
        "rest_id": "200",
        "core": {
            "user_results": {
                "result": {
                    "rest_id": "30",
                    "core": {
                        "screen_name": "target_author",
                        "name": "Target Author",
                    },
                    "is_blue_verified": True,
                    "verification": {
                        "verified": False,
                    },
                }
            }
        },
        "legacy": {
            "id_str": "200",
            "created_at": "Sat Aug 17 12:22:47 +0000 2024",
            "full_text": "One-hop target post",
            "favorite_count": 100,
            "retweet_count": 20,
            "reply_count": 10,
            "quote_count": 5,
            "entities": {},
        },
        "views": {
            "count": "5000",
        },
    }

    post = mapper.map_target(record)

    assert post.post_id == "200"

    assert post.author.user_id == "30"
    assert post.author.username == "target_author"
    assert post.author.display_name == "Target Author"
    assert post.author.verified is True

    assert post.text == "One-hop target post"
    assert post.published_at.year == 2024

    assert post.reply_to_post_id is None
    assert post.quoted_post_id is None
    assert post.reposted_post_id is None

    assert post.hashtags == ()
    assert post.mentions == ()

    assert post.metrics.like_count == 100
    assert post.metrics.repost_count == 20
    assert post.metrics.reply_count == 10
    assert post.metrics.quote_count == 5
    assert post.metrics.view_count == 5000