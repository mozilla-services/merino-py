# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for merino.providers.wcs.protocol."""

from merino.providers.suggest.sports.backends.sportsdata.common import GameStatus
from merino.providers.wcs.protocol import EventInfo
from tests.wcs.factories import event


def test_event_info_from_event_builds_world_cup_query() -> None:
    """`query` uses the World Cup 2026 prefix and date string."""
    e = event(
        event_id=1,
        day_offset=0,
        hour=14,
        home=("BRA", "Brazil", 90000001),
        away=("ARG", "Argentina", 90000002),
        status=GameStatus.Scheduled,
    )

    info = EventInfo.from_event(e)

    expected_date = e.date.strftime("%d %B %Y")
    assert info.query == f"World Cup 2026 Brazil vs Argentina {expected_date}"
