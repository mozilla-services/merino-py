"""Unit test for ranker algorithms used to rank curated recommendations."""

import uuid

import pytest
import random

from pydantic import HttpUrl
from merino.curated_recommendations.corpus_backends.protocol import Topic
from merino.curated_recommendations.layouts import layout_4_medium, layout_4_large, layout_6_tiles
from merino.curated_recommendations.protocol import (
    CuratedRecommendation,
    MIN_TILE_ID,
    CuratedRecommendationsFeed,
    Section,
    SectionConfiguration,
)
from merino.curated_recommendations.rankers import (
    spread_publishers,
    boost_preferred_topic,
    boost_followed_sections,
)


class TestCuratedRecommendationsProviderSpreadPublishers:
    """Unit tests for spread_publishers."""

    @staticmethod
    def generate_recommendations(item_ids: list[str]) -> list[CuratedRecommendation]:
        """Create dummy recommendations for the tests below."""
        recs = []
        for item_id in item_ids:
            rec = CuratedRecommendation(
                corpusItemId=str(uuid.uuid4()),
                tileId=MIN_TILE_ID + random.randint(0, 101),
                receivedRank=random.randint(0, 101),
                scheduledCorpusItemId=item_id,
                url=HttpUrl("https://littlelarry.com/"),
                title="little larry",
                excerpt="is failing english",
                topic=random.choice(list(Topic)),
                publisher="cohens",
                isTimeSensitive=False,
                imageUrl=HttpUrl("https://placehold.co/600x400/"),
                iconUrl=None,
            )

            recs.append(rec)

        return recs

    def test_spread_publishers_single_reorder(self):
        """Should only re-order one element."""
        recs = self.generate_recommendations(["1", "2", "3", "4", "5", "6", "7", "8"])
        recs[0].publisher = "thedude.com"
        recs[1].publisher = "walter.com"
        recs[2].publisher = "donnie.com"
        recs[3].publisher = "thedude.com"
        recs[4].publisher = "innout.com"
        recs[5].publisher = "bowling.com"
        recs[6].publisher = "walter.com"
        recs[7].publisher = "abides.com"

        reordered = spread_publishers(recs, spread_distance=3)

        # ensure the elements are re-ordered in the way we expect

        # this domain check is redundant, but it's kind of a nice illustration of what we expect and is easier
        # to read than the item ids, so i'm leaving it
        assert [x.publisher for x in reordered] == [
            "thedude.com",
            "walter.com",
            "donnie.com",
            "innout.com",
            "thedude.com",
            "bowling.com",
            "walter.com",
            "abides.com",
        ]
        assert [x.scheduledCorpusItemId for x in reordered] == [
            "1",
            "2",
            "3",
            "5",
            "4",
            "6",
            "7",
            "8",
        ]

    def test_spread_publishers_multiple_reorder(self):
        """Should re-order multiple elements."""
        recs = self.generate_recommendations(["1", "2", "3", "4", "5", "6", "7", "8"])
        recs[0].publisher = "thedude.com"
        recs[1].publisher = "walter.com"
        recs[2].publisher = "walter.com"
        recs[3].publisher = "thedude.com"
        recs[4].publisher = "innout.com"
        recs[5].publisher = "innout.com"
        recs[6].publisher = "donnie.com"
        recs[7].publisher = "abides.com"

        reordered = spread_publishers(recs, spread_distance=3)

        # ensure the elements are re-ordered in the way we expect

        # this domain check is redundant, but it's kind of a nice illustration of what we expect and is easier
        # to read than the item ids, so i'm leaving it
        assert [x.publisher for x in reordered] == [
            "thedude.com",
            "walter.com",
            "innout.com",
            "donnie.com",
            "thedude.com",
            "walter.com",
            "innout.com",
            "abides.com",
        ]
        assert [x.scheduledCorpusItemId for x in reordered] == [
            "1",
            "2",
            "5",
            "7",
            "4",
            "3",
            "6",
            "8",
        ]

    def test_spread_publishers_give_up_at_the_end(self):
        """Should not re-order when the end of the list cannot satisfy the requested spread."""
        recs = self.generate_recommendations(["1", "2", "3", "4", "5", "6", "7", "8"])
        recs[0].publisher = "thedude.com"
        recs[1].publisher = "abides.com"
        recs[2].publisher = "walter.com"
        recs[3].publisher = "donnie.com"
        recs[4].publisher = "donnie.com"
        recs[5].publisher = "innout.com"
        recs[6].publisher = "donnie.com"
        recs[7].publisher = "innout.com"

        reordered = spread_publishers(recs, spread_distance=3)

        # ensure the elements are re-ordered in the way we expect

        # if the number of elements at the end of the list cannot satisfy the spread, we give up and just append
        # the remainder
        assert [x.scheduledCorpusItemId for x in reordered] == [
            "1",
            "2",
            "3",
            "4",
            "6",
            "5",
            "7",
            "8",
        ]

    def test_spread_publishers_cannot_spread(self):
        """If we don't have enough variance in publishers, spread can't happen."""
        recs = self.generate_recommendations(["1", "2", "3", "4", "5", "6", "7", "8"])
        recs[0].publisher = "thedude.com"
        recs[1].publisher = "abides.com"
        recs[2].publisher = "donnie.com"
        recs[3].publisher = "donnie.com"
        recs[4].publisher = "thedude.com"
        recs[5].publisher = "abides.com"
        recs[6].publisher = "thedude.com"
        recs[7].publisher = "donnie.com"

        reordered = spread_publishers(recs, spread_distance=3)

        # ensure the elements aren't reordered at all (as we don't have enough publisher variance)
        assert [x.scheduledCorpusItemId for x in reordered] == [
            "1",
            "2",
            "3",
            "4",
            "5",
            "6",
            "7",
            "8",
        ]


class TestCuratedRecommendationsProviderBoostPreferredTopic:
    """Unit tests for boost_preferred_topic & is_boostable."""

    @staticmethod
    def generate_recommendations(topics: list[Topic]) -> list[CuratedRecommendation]:
        """Create dummy recommendations for the tests below with specific topics."""
        recs = []
        i = 1
        for topic in topics:
            rec = CuratedRecommendation(
                corpusItemId=str(uuid.uuid4()),
                tileId=MIN_TILE_ID + random.randint(0, 101),
                receivedRank=i,
                scheduledCorpusItemId=str(i),
                url=HttpUrl("https://littlelarry.com/"),
                title="little larry",
                excerpt="is failing english",
                topic=topic,
                publisher="cohens",
                isTimeSensitive=False,
                imageUrl=HttpUrl("https://placehold.co/600x400/"),
                iconUrl=None,
            )
            recs.append(rec)
            i += 1
        return recs

    def test_boost_preferred_topic_two_topics(self):
        """If two preferred topics are provided but only one topic is found in list or recs, boost first 2 recs
        to first two slots.
        """
        recs = self.generate_recommendations(
            [Topic.TRAVEL, Topic.ARTS, Topic.SPORTS, Topic.FOOD, Topic.EDUCATION, Topic.FOOD]
        )
        # career topic is not present in rec list, boost item with food topic to second slot
        reordered_recs = boost_preferred_topic(recs, [Topic.CAREER, Topic.FOOD])

        assert len(recs) == len(reordered_recs)
        # for readability
        assert reordered_recs[0].topic == Topic.FOOD
        assert reordered_recs[0].scheduledCorpusItemId == "4"
        assert reordered_recs[1].topic == Topic.FOOD
        assert reordered_recs[1].scheduledCorpusItemId == "6"

    @pytest.mark.parametrize(
        "preferred_topics, expected_topics, expected_ids",
        [
            # Test case for 1 preferred topic
            (
                [Topic.EDUCATION],
                [Topic.EDUCATION, Topic.EDUCATION],
                ["6", "16"],
            ),
            # Test case for 2 preferred topics
            (
                [Topic.POLITICS, Topic.EDUCATION],
                [Topic.EDUCATION, Topic.POLITICS, Topic.POLITICS, Topic.EDUCATION],
                ["6", "9", "12", "16"],
            ),
            # Test case for 5 preferred topics
            (
                [Topic.POLITICS, Topic.EDUCATION, Topic.TRAVEL, Topic.BUSINESS, Topic.ARTS],
                [
                    Topic.BUSINESS,
                    Topic.TRAVEL,
                    Topic.ARTS,
                    Topic.EDUCATION,
                    Topic.TRAVEL,
                    Topic.POLITICS,
                    Topic.ARTS,
                    Topic.POLITICS,
                    Topic.BUSINESS,
                    Topic.EDUCATION,
                ],
                ["1", "2", "3", "6", "8", "9", "10", "12", "14", "16"],
            ),
            # Test case for 6+ preferred topics (assuming max 10 items in total)
            (
                [
                    Topic.GAMING,
                    Topic.POLITICS,
                    Topic.EDUCATION,
                    Topic.TRAVEL,
                    Topic.BUSINESS,
                    Topic.ARTS,
                ],
                [
                    Topic.BUSINESS,
                    Topic.TRAVEL,
                    Topic.ARTS,
                    Topic.EDUCATION,
                    Topic.GAMING,
                    Topic.TRAVEL,
                    Topic.POLITICS,
                    Topic.ARTS,
                    Topic.POLITICS,
                    Topic.BUSINESS,
                ],
                ["1", "2", "3", "6", "7", "8", "9", "10", "12", "14"],
            ),
        ],
    )
    def test_boost_preferred_topic(self, preferred_topics, expected_topics, expected_ids):
        """Test boosting works correctly for 1, 2, 5, 6+ preferred topics & that expected topics
        & recommendation ids are in the correct positions.
        """
        recs = self.generate_recommendations(
            [
                Topic.BUSINESS,  # 1
                Topic.TRAVEL,  # 2
                Topic.ARTS,  # 3
                Topic.SPORTS,  # 4
                Topic.FOOD,  # 5
                Topic.EDUCATION,  # 6
                Topic.GAMING,  # 7
                Topic.TRAVEL,  # 8
                Topic.POLITICS,  # 9
                Topic.ARTS,  # 10
                Topic.ARTS,  # 11
                Topic.POLITICS,  # 12
                Topic.SPORTS,  # 13
                Topic.BUSINESS,  # 14
                Topic.PARENTING,  # 15
                Topic.EDUCATION,  # 16
                Topic.BUSINESS,  # 17
                Topic.FOOD,  # 18
                Topic.GAMING,  # 19
                Topic.POLITICS,  # 20
            ]
        )

        reordered_recs = boost_preferred_topic(recs, preferred_topics)

        # Check that the length of the reordered recommendations matches
        assert len(reordered_recs) == len(recs)

        # Check that the expected topics and IDs are in the correct positions
        for idx, (expected_topic, expected_id) in enumerate(zip(expected_topics, expected_ids)):
            assert reordered_recs[idx].topic == expected_topic.value
            assert reordered_recs[idx].scheduledCorpusItemId == expected_id

    def test_boost_preferred_topic_no_preferred_topic_found(self):
        """Don't reorder list of recs if no items with preferred topics are found."""
        recs = self.generate_recommendations(
            [Topic.POLITICS, Topic.ARTS, Topic.SPORTS, Topic.FOOD, Topic.PERSONAL_FINANCE]
        )
        reordered_recs = boost_preferred_topic(recs, [Topic.CAREER])

        assert len(recs) == len(reordered_recs)
        # assert that the order of recs has not changed since recs don't have preferred topic
        assert reordered_recs == recs

    def test_boost_preferred_topic_no_reorder(self):
        """Should not reorder list of recs if all preferred topics are not in the top N slots (2 recs per topic)"""
        recs = self.generate_recommendations(
            [
                Topic.TRAVEL,
                Topic.TRAVEL,
                Topic.EDUCATION,
                Topic.SPORTS,
                Topic.EDUCATION,
                Topic.SPORTS,
            ]
        )
        # should return true as recs with TRAVEL topic are in the first two slots, but 3rd slot is occupied by ARTS
        # topic but should be occupied with SPORTS topic
        not_reordered_recs = boost_preferred_topic(
            recs, [Topic.TRAVEL, Topic.EDUCATION, Topic.SPORTS]
        )

        assert recs == not_reordered_recs


class TestCuratedRecommendationsProviderBoostFollowedSections:
    """Unit tests for boost_followed_sections"""

    @staticmethod
    def generate_curated_recommendations_feed_sections(
        received_feed_ranks: list[int], section_ids: list[str]
    ) -> CuratedRecommendationsFeed:
        """Create dummy sections & construct dummy CuratedRecommendationsFeed object for the tests below with
        specific receivedFeedRank per section.
        """
        sections = []
        layout_order = [layout_4_medium, layout_4_large, layout_6_tiles]
        i = 1
        for rank in received_feed_ranks:
            section = Section(
                receivedFeedRank=rank,
                recommendations=[],
                title="Fake Section Title " + str(i),
                layout=layout_order[0],
            )
            sections.append(section)
            i += 1

        feed = CuratedRecommendationsFeed()
        for section_id, section in zip(section_ids, sections):
            setattr(feed, section_id, section)  # Dynamically set Section attributes

        return feed

    def test_boost_followed_sections(self):
        """Test boosting sections works properly. Followed & unfollowed sections should
        maintain their relative order.
        """
        req_sections = [
            SectionConfiguration(sectionId="arts", isFollowed=True, isBlocked=False),
            SectionConfiguration(sectionId="business", isFollowed=True, isBlocked=False),
            SectionConfiguration(sectionId="travel", isFollowed=False, isBlocked=True),
        ]
        feed = self.generate_curated_recommendations_feed_sections(
            [0, 5, 3, 2, 6], ["top_stories_section", "arts", "food", "business", "travel"]
        )
        # Let's first assert original feed received ranks
        assert feed.top_stories_section.receivedFeedRank == 0
        assert feed.business.receivedFeedRank == 2
        assert feed.food.receivedFeedRank == 3
        assert feed.arts.receivedFeedRank == 5
        assert feed.travel.receivedFeedRank == 6

        # Get the updated feed with boosted followed sections
        new_feed = boost_followed_sections(req_sections, feed)

        # Now let's assert the updated feed and check that followed sections were boosted

        # Assertions for receivedFeedRank
        assert new_feed.top_stories_section.receivedFeedRank == 0  # should always remain 0
        assert new_feed.business.receivedFeedRank == 1  # had a rank==2, should now be 1
        assert new_feed.arts.receivedFeedRank == 2
        assert new_feed.food.receivedFeedRank == 3
        assert (
            new_feed.travel.receivedFeedRank == 4
        )  # originally ranked after Food, should still be after

        # Assertions for isFollowed
        assert new_feed.arts.isFollowed
        assert new_feed.business.isFollowed
        assert not new_feed.food.isFollowed
        assert not new_feed.travel.isFollowed

    def test_boost_followed_sections_no_followed_sections_found_block_section(self):
        """Test boosting sections only boosts followed sections. If no followed sections found in request,
        section order should remain the same.
        """
        req_sections = [
            SectionConfiguration(sectionId="arts", isFollowed=False, isBlocked=False),
            SectionConfiguration(sectionId="business", isFollowed=False, isBlocked=True),
            SectionConfiguration(sectionId="travel", isFollowed=False, isBlocked=True),
        ]
        feed = self.generate_curated_recommendations_feed_sections(
            [0, 5, 3, 2, 6], ["top_stories_section", "arts", "food", "business", "travel"]
        )
        # Let's first assert original feed received ranks
        assert feed.top_stories_section.receivedFeedRank == 0
        assert feed.business.receivedFeedRank == 2
        assert feed.food.receivedFeedRank == 3
        assert feed.arts.receivedFeedRank == 5
        assert not feed.business.isBlocked  # isBlocked should be false by default
        assert feed.travel.receivedFeedRank == 6
        assert not feed.travel.isBlocked  # isBlocked should be false by default

        # Get the updated feed with boosted followed sections
        new_feed = boost_followed_sections(req_sections, feed)

        # Now let's assert the updated feed and check that receivedFeedRank has not changed for sections

        # Assertions for receivedFeedRank
        assert new_feed.top_stories_section.receivedFeedRank == 0
        assert new_feed.business.receivedFeedRank == 2
        assert new_feed.food.receivedFeedRank == 3
        assert new_feed.arts.receivedFeedRank == 5
        assert new_feed.travel.receivedFeedRank == 6

        # Assertions for isFollowed & isBlocked
        assert not new_feed.arts.isFollowed
        assert not new_feed.food.isFollowed
        assert not new_feed.business.isFollowed
        assert new_feed.business.isBlocked  # isBlocked should be now true
        assert not new_feed.travel.isFollowed
        assert new_feed.travel.isBlocked  # isBlocked should be now true
