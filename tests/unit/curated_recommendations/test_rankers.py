"""Unit test for ranker algorithms used to rank curated recommendations."""

import uuid

import pytest
import random
from datetime import datetime, timezone
import freezegun
from freezegun import freeze_time

from pydantic import HttpUrl
from merino.curated_recommendations.corpus_backends.protocol import Topic
from merino.curated_recommendations.layouts import layout_4_medium, layout_4_large, layout_6_tiles
from merino.curated_recommendations.protocol import (
    CuratedRecommendation,
    MIN_TILE_ID,
    Section,
    SectionConfiguration,
    InferredInterests,
)
from merino.curated_recommendations.rankers import (
    spread_publishers,
    boost_preferred_topic,
    boost_followed_sections,
    is_section_recently_followed,
    renumber_recommendations,
    put_top_stories_first,
    greedy_personalized_section_rank,
)
from tests.unit.curated_recommendations.fixtures import (
    generate_recommendations,
    generate_sections_feed,
)


class TestRenumberRecommendations:
    """Tests for the renumber_recommendations function."""

    def test_empty_list(self):
        """Test that renumber_recommendations works with an empty list."""
        recs: list[CuratedRecommendation] = []
        renumber_recommendations(recs)
        assert recs == []

    def test_sequential_order(self):
        """Test that renumber_recommendations assigns sequential ranks."""
        recs = generate_recommendations(item_ids=["1", "2", "3", "4", "5"])
        renumber_recommendations(recs)
        assert [rec.receivedRank for rec in recs] == list(range(len(recs)))

    def test_preserve_order_for_equal_ranks(self):
        """Test renumber_recommendations preserves original order for equal initial ranks."""
        recs = generate_recommendations(item_ids=["1", "2", "3", "4"])
        # Set all recommendations to the same initial rank.
        for rec in recs:
            rec.receivedRank = 5
        original_order = [rec.corpusItemId for rec in recs]
        renumber_recommendations(recs)
        assert [rec.corpusItemId for rec in recs] == original_order
        assert [rec.receivedRank for rec in recs] == list(range(len(recs)))


class TestCuratedRecommendationsProviderSpreadPublishers:
    """Unit tests for spread_publishers."""

    def test_spread_publishers_single_reorder(self):
        """Should only re-order one element."""
        recs = generate_recommendations(item_ids=["1", "2", "3", "4", "5", "6", "7", "8"])
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
        assert [x.corpusItemId for x in reordered] == [
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
        recs = generate_recommendations(item_ids=["1", "2", "3", "4", "5", "6", "7", "8"])
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
        assert [x.corpusItemId for x in reordered] == [
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
        recs = generate_recommendations(item_ids=["1", "2", "3", "4", "5", "6", "7", "8"])
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
        assert [x.corpusItemId for x in reordered] == [
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
        recs = generate_recommendations(item_ids=["1", "2", "3", "4", "5", "6", "7", "8"])
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
        assert [x.corpusItemId for x in reordered] == [
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


class TestIsSectionRecentlyFollowed:
    """Unit tests for is_section_recently_followed"""

    @freezegun.freeze_time("2025-03-20 12:00:00", tz_offset=0)
    def test_is_section_recently_followed_one_week_ago(self):
        """Should return True if section was followed exactly 1 week ago"""
        # Followed exactly 7 days ago
        followed_at = datetime(2025, 3, 13, 12, 0, 0, tzinfo=timezone.utc)
        assert is_section_recently_followed(followed_at) is True

    @freezegun.freeze_time("2025-03-20 12:00:00", tz_offset=0)
    def test_is_section_recently_followed_now(self):
        """Should return True if section is followed right now"""
        # Followed now
        followed_at = datetime(2025, 3, 20, 12, 0, 0, tzinfo=timezone.utc)
        assert is_section_recently_followed(followed_at) is True

    @freezegun.freeze_time("2025-03-20 12:00:00", tz_offset=0)
    def test_is_section_recently_followed_more_than_one_week_ago(self):
        """Should return False if section was followed more than 1 week ago"""
        # Followed now
        followed_at = datetime(2025, 3, 12, 12, 0, 0, tzinfo=timezone.utc)
        assert is_section_recently_followed(followed_at) is False

    @freezegun.freeze_time("2025-03-20 12:00:00", tz_offset=0)
    def test_is_section_recently_followed_none(self):
        """Should return False if followed_at is None"""
        assert is_section_recently_followed(None) is False


class TestCuratedRecommendationsProviderBoostFollowedSections:
    """Unit tests for boost_followed_sections"""

    @staticmethod
    def generate_sections(
        received_feed_ranks: list[int], section_ids: list[str]
    ) -> dict[str, Section]:
        """Create a dictionary of dummy sections with specific receivedFeedRank per section."""
        sections = {}
        layout_order = [layout_4_medium, layout_4_large, layout_6_tiles]
        for rank, section_id in zip(received_feed_ranks, section_ids):
            sections[section_id] = Section(
                receivedFeedRank=rank,
                recommendations=[],  # Dummy recommendations.
                title=section_id,
                layout=layout_order[0],
            )
        return sections

    @freeze_time("2025-03-20 12:00:00", tz_offset=0)
    @pytest.mark.parametrize(
        ("followed_section", "original_received_feed_rank"),
        [
            (SectionConfiguration(sectionId="business", isFollowed=True, isBlocked=False), 1),
            (SectionConfiguration(sectionId="career", isFollowed=True, isBlocked=False), 2),
            (SectionConfiguration(sectionId="arts", isFollowed=True, isBlocked=False), 3),
            (SectionConfiguration(sectionId="food", isFollowed=True, isBlocked=False), 4),
            (SectionConfiguration(sectionId="health", isFollowed=True, isBlocked=False), 5),
            (SectionConfiguration(sectionId="home", isFollowed=True, isBlocked=False), 6),
            (SectionConfiguration(sectionId="finance", isFollowed=True, isBlocked=False), 7),
            (SectionConfiguration(sectionId="government", isFollowed=True, isBlocked=False), 8),
            (SectionConfiguration(sectionId="sports", isFollowed=True, isBlocked=False), 9),
            (SectionConfiguration(sectionId="tech", isFollowed=True, isBlocked=False), 10),
            (SectionConfiguration(sectionId="travel", isFollowed=True, isBlocked=False), 11),
            (SectionConfiguration(sectionId="education", isFollowed=True, isBlocked=False), 12),
            (SectionConfiguration(sectionId="hobbies", isFollowed=True, isBlocked=False), 13),
            (
                SectionConfiguration(
                    sectionId="society-parenting", isFollowed=True, isBlocked=False
                ),
                14,
            ),
            (
                SectionConfiguration(
                    sectionId="education-science", isFollowed=True, isBlocked=False
                ),
                15,
            ),
            (SectionConfiguration(sectionId="society", isFollowed=True, isBlocked=False), 16),
        ],
    )
    def test_boost_followed_section_for_every_section(
        self, followed_section, original_received_feed_rank
    ):
        """Test boosting sections works properly for each section."""
        req_sections = [followed_section]

        # Generate feed with all sections as a dict using the correct keys.
        feed = self.generate_sections(
            list(range(17)),
            [
                "top_stories_section",  # 0
                "business",  # 1
                "career",  # 2
                "arts",  # 3
                "food",  # 4
                "health",  # 5
                "home",  # 6
                "finance",  # 7
                "government",  # 8
                "sports",  # 9
                "tech",  # 10
                "travel",  # 11
                "education",  # 12
                "hobbies",  # 13
                "society-parenting",  # 14
                "education-science",  # 15
                "society",  # 16
            ],
        )
        # Assert original feed received ranks.
        assert feed["top_stories_section"].receivedFeedRank == 0
        assert feed[followed_section.sectionId].receivedFeedRank == original_received_feed_rank

        # Get the updated feed with boosted followed sections.
        new_feed = boost_followed_sections(req_sections, feed)

        # Followed section should have receivedFeedRank == 0.
        assert new_feed[followed_section.sectionId].receivedFeedRank == 0

        # Assertions for isFollowed.
        assert new_feed[followed_section.sectionId].isFollowed

    @freeze_time("2025-03-20 12:00:00", tz_offset=0)
    def test_boost_followed_sections_with_followed_at(self):
        """Test boosting sections works properly when following more than 1 section.
        Followed sections should be ranked based on followed_at. Followed & unfollowed sections should maintain their relative order.
        """
        req_sections = [
            SectionConfiguration(
                sectionId="hobbies",
                isFollowed=True,
                isBlocked=False,
                followedAt=datetime(2025, 3, 18, tzinfo=timezone.utc),  # Followed on 03/18
            ),  # maps to hobbies section
            SectionConfiguration(
                sectionId="tech",
                isFollowed=True,
                isBlocked=False,
                followedAt=datetime(2025, 3, 10, tzinfo=timezone.utc),  # Followed on 03/10
            ),  # maps to tech section
            SectionConfiguration(
                sectionId="travel", isFollowed=False, isBlocked=True
            ),  # maps to travel section
        ]
        feed = self.generate_sections(
            [0, 5, 3, 2, 6],
            ["top_stories_section", "hobbies", "food", "tech", "travel"],
        )
        # Assert original feed received ranks.
        assert feed["top_stories_section"].receivedFeedRank == 0
        assert feed["tech"].receivedFeedRank == 2
        assert feed["food"].receivedFeedRank == 3
        assert feed["hobbies"].receivedFeedRank == 5
        assert feed["travel"].receivedFeedRank == 6

        # Get the updated feed with boosted followed sections.
        new_feed = boost_followed_sections(req_sections, feed)

        # Assertions for receivedFeedRank.
        # 'hobbies' was followed more recently so should be boosted to rank 0.
        assert new_feed["hobbies"].receivedFeedRank == 0
        # 'tech' remains at rank 2.
        assert new_feed["tech"].receivedFeedRank == 1
        assert new_feed["top_stories_section"].receivedFeedRank == 2
        # 'food' remains at rank 3.
        assert new_feed["food"].receivedFeedRank == 3
        # 'travel' should come after food.
        assert new_feed["travel"].receivedFeedRank == 4

        # Assertions for isFollowed.
        assert new_feed["hobbies"].isFollowed
        assert new_feed["tech"].isFollowed
        assert not new_feed["food"].isFollowed
        assert not new_feed["travel"].isFollowed

    def test_boost_followed_sections_no_followed_sections_found_block_section(self):
        """Test boosting sections only boosts followed sections.
        If no followed sections found in request, section order should be updated based on blocked status.
        """
        req_sections = [
            SectionConfiguration(sectionId="arts", isFollowed=False, isBlocked=False),
            SectionConfiguration(sectionId="business", isFollowed=False, isBlocked=True),
            SectionConfiguration(sectionId="travel", isFollowed=False, isBlocked=True),
        ]
        feed = self.generate_sections(
            [0, 5, 3, 2, 6],
            ["top_stories_section", "arts", "food", "business", "travel"],
        )
        # Assert original feed received ranks.
        assert feed["top_stories_section"].receivedFeedRank == 0
        assert feed["business"].receivedFeedRank == 2
        assert feed["food"].receivedFeedRank == 3
        assert feed["arts"].receivedFeedRank == 5
        assert not feed["business"].isBlocked  # isBlocked should be false by default
        assert feed["travel"].receivedFeedRank == 6
        assert not feed["travel"].isBlocked  # isBlocked should be false by default

        # Get the updated feed with boosted followed sections.
        new_feed = boost_followed_sections(req_sections, feed)

        # Now assert updated receivedFeedRank.
        assert new_feed["top_stories_section"].receivedFeedRank == 0
        expected_ranks = [1, 2, 3, 4]
        actual_ranks = [
            new_feed[s].receivedFeedRank for s in ["business", "food", "arts", "travel"]
        ]
        assert sorted(actual_ranks) == expected_ranks

        # Assertions for isFollowed & isBlocked.
        assert not new_feed["arts"].isFollowed
        assert not new_feed["food"].isFollowed
        assert not new_feed["business"].isFollowed
        assert new_feed["business"].isBlocked
        assert not new_feed["travel"].isFollowed
        assert new_feed["travel"].isBlocked


class TestPutTopStoriesFirst:
    """Tests covering put_top_stories_first"""

    def test_shifts_ranks_when_not_at_zero(self):
        """Test that when top_stories_section has a non-zero rank, it is moved to the top."""
        # Create 4 sections; default top_stories_section at rank 0
        sections = generate_sections_feed(section_count=4)
        # Get swap 'Top Stories' with the section on index 2.
        keys: list[str] = list(sections.keys())
        keys[0], keys[2] = keys[2], keys[0]
        for idx, sid in enumerate(keys):
            sections[sid].receivedFeedRank = idx

        sections = put_top_stories_first(sections)

        # Expected: top_stories_section first, then rest in keys order without top
        expected_order = ["top_stories_section"] + [k for k in keys if k != "top_stories_section"]
        for idx, sid in enumerate(expected_order):
            assert sections[sid].receivedFeedRank == idx

    def test_no_change_when_already_zero(self):
        """Ensure that if top_stories_section is already at rank 0, no ranks are altered."""
        # Default fixture has top_stories_section at 0
        feed = generate_sections_feed(section_count=3)
        original = {sid: sec.receivedFeedRank for sid, sec in feed.items()}

        updated = put_top_stories_first(feed)

        # No ranks should change
        assert {sid: sec.receivedFeedRank for sid, sec in updated.items()} == original

    def test_no_error_when_missing_top_stories(self):
        """Ensure function returns unchanged feed when top_stories_section is absent."""
        # Construct a feed without top_stories_section
        from merino.curated_recommendations.layouts import layout_4_medium

        feed = {
            "foo": Section(
                receivedFeedRank=2,
                recommendations=[],
                title="Foo",
                layout=layout_4_medium,
            )
        }

        # Should simply return the same dict
        updated = put_top_stories_first(feed)
        assert updated is feed


class TestGreedyPersonalizedSectionRanker:
    """Tests greedy use of inferred section ranker"""

    def test_expected_ranking(self):
        """Tests putting sections from inferred interests first"""
        # get example section feed
        sections = generate_sections_feed(section_count=16)
        # extract titles and build InferredInterests
        sec_titles = [sec for sec in sections]
        personal_sections = [sec_titles[i] for i in [4, 10, 13, 15]]
        personal_interests = InferredInterests({k: i for i, k in enumerate(personal_sections)})
        # store original order of sections not in inferredInterests
        original_order = sorted(sections, key=lambda x: sections[x].receivedFeedRank)
        original_order = [
            k
            for k in original_order
            if k not in personal_sections or personal_interests.root[k] < 0.0092
        ]
        # rerank the sections
        reranked_sections = greedy_personalized_section_rank(
            sections=sections, personal_interests=personal_interests, epsilon=0.0
        )

        # personal_interests should be at the top of reranked_sections, reversed
        # the last section in personal_interests has 0 value, doesnt meet minimum
        # and diverts to original ranking
        for i, s in enumerate(personal_sections[::-1][:-1]):
            print(i, s)
            assert i == reranked_sections[s].receivedFeedRank
        # original order should be preserved, -1 due to 0 value in personal interests
        for i, s in enumerate(original_order):
            print(i, s)
            assert i + len(personal_sections) - 1 == reranked_sections[s].receivedFeedRank

    def test_empty_interests(self):
        """Empty inferredinterests should not affect the section ranking"""
        # get example section feed
        sections = generate_sections_feed(section_count=16)
        # store the original ranking
        original_ranking = {sec: sections[sec].receivedFeedRank for sec in sections}
        # inferredinterests is empty
        personal_interests = InferredInterests({})
        # rerank the sections
        reranked_sections = greedy_personalized_section_rank(
            sections=sections, personal_interests=personal_interests, epsilon=0.0
        )
        # the ranking should not have changed
        for sec in reranked_sections:
            assert reranked_sections[sec].receivedFeedRank == original_ranking[sec]

    def test_fictional_interests(self):
        """Interest vector keys that are not sections should not appear in section ranking"""
        # get example section feed
        sections = generate_sections_feed(section_count=16)
        # inferredinterests is empty
        bogus = "asflkjdfoij"
        personal_interests = InferredInterests({bogus: 1.0})
        # rerank the sections
        reranked_sections = greedy_personalized_section_rank(
            sections=sections, personal_interests=personal_interests, epsilon=0.0
        )
        # the sections should not include bogus
        assert bogus not in reranked_sections
