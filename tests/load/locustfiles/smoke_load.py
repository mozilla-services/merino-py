# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Load test shape module."""

import os
from typing import Type

from locust import LoadTestShape, User
from pydantic import BaseModel

from locustfile import MerinoUser

TickTuple = tuple[int, float, list[Type[User]] | None]


class ShapeStage(BaseModel):
    """Data defining a shape stage."""

    run_time: int
    users: int
    spawn_rate: float
    user_classes: list[Type[User]] = [MerinoUser]


class MerinoSmokeLoadTestShape(LoadTestShape):
    """A load test shape class for Merino (Duration: 5 minutes, Users: 25).

    The smoke load test verifies the system's performance under minimal load.
    The test is run for a short period, possibly in CD, to ensure the system is working correctly.

    Note: The Shape class assumes that the workers can support the generated spawn rates. Should
    the number of available Locust workers change or should the Locust worker capacity change,
    the WORKERS_COUNT and USERS_PER_WORKER values must be changed respectively.
    """

    RUN_TIME: int = 300  # 5 minutes (must not be set to less than 1 minute)
    # Must match value defined in setup_k8s.sh
    WORKER_COUNT: int = int(os.environ.get("WORKER_COUNT", 5))
    # Number of users supported on a worker running on a n1-standard-2
    USERS_PER_WORKER: int = int(os.environ.get("USERS_PER_WORKER", 3))
    USERS: int = WORKER_COUNT * USERS_PER_WORKER

    stages: list[ShapeStage]

    def __init__(self) -> None:
        super(LoadTestShape, self).__init__()

        spawn_rate: float = round(self.USERS / 60, 2)
        self.stages = [
            # Stage 1: Spawn users in the first minute and dwell until the last minute
            ShapeStage(
                run_time=(self.RUN_TIME - 60),
                users=self.USERS,
                spawn_rate=spawn_rate,
            ),
            # Stage 2: Stop users in the last minute
            ShapeStage(run_time=self.RUN_TIME, users=0, spawn_rate=spawn_rate),
        ]

    def tick(self) -> TickTuple | None:
        """Override defining the desired distribution for Merino load testing.

        Returns:
            TickTuple: Distribution parameters
                user_count: Total user count
                spawn_rate: Number of users to start/stop per second when changing
                            number of users
                user_classes: None or a List of user classes to be spawned
            None: Instruction to stop the load test
        """
        for stage in self.stages:
            if self.get_run_time() < stage.run_time:
                return stage.users, stage.spawn_rate, stage.user_classes
        return None
