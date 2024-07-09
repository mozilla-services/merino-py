# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Load test for the /api/v1/curated-recommendations endpoint."""

import logging
import os
import random
from locust import HttpUser, run_single_user, task

from merino.curated_recommendations.provider import Locale, CuratedRecommendationsRequest
from tests.load.common.client_info import DESKTOP_FIREFOX

LOGGING_LEVEL = os.environ["LOAD_TESTS__LOGGING_LEVEL"]
logger = logging.getLogger("load_tests")
logger.setLevel(int(LOGGING_LEVEL))

CURATED_RECOMMENDATIONS_API = "/api/v1/curated-recommendations"


class CuratedRecommendationsUser(HttpUser):
    """User that sends requests to the Curated Recommendations API."""

    @task
    def get_curated_recommendations(self) -> None:
        """Send request to get curated recommendations."""
        self._request_recommendations(
            CuratedRecommendationsRequest(
                locale=random.choice(list(Locale)),
                count=100,
            )
        )

    def _request_recommendations(self, data: CuratedRecommendationsRequest) -> None:
        """Request recommendations from Merino for the given data.

        Args:
            data: CuratedRecommendationsRequest object containing request data
        """
        with self.client.post(
            url=CURATED_RECOMMENDATIONS_API,
            json=data.model_dump(),
            headers={"User-Agent": random.choice(DESKTOP_FIREFOX)},
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"{response.status_code=}, expected 200, {response.text=}")
                return

            response.success()


# if launched directly, e.g. "python curated_recommendations.py", not "locust -f debugging.py"
if __name__ == "__main__":
    run_single_user(CuratedRecommendationsUser)
