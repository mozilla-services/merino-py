"""Thompson sampling optimizer."""

import numpy as np

from scipy.stats import beta

from merino.optimizers.models import ThompsonCandidate, ThompsonConfig


class ThompsonSampler:
    """Thompson sampling optimizer."""

    config: ThompsonConfig

    def __init__(self, config: ThompsonConfig) -> None:
        self.config = config

    def sample(self, candidates: list[ThompsonCandidate]) -> ThompsonCandidate | None:
        """Apply Thompson sampling to a set of candidates.

        A dummy candidate can be set in `self.config` serving as a "guard"
        to ensure the winner meets the minimal requirement.

        Params:
            - `candidates`: a list of candidates of type `ThompsonCandidate`.
        Returns:
            A selected candidate or None if no candidate wins.
        """
        if not candidates:
            return None

        samples = [
            beta.rvs(
                c.metrics.engaged, c.metrics.not_engaged, random_state=self.config.random_seed
            )
            for c in candidates
        ]

        n = np.argmax(samples)
        sample = samples[n]

        if (
            self.config.dummy_candidate
            and beta.rvs(
                self.config.dummy_candidate.engaged,
                self.config.dummy_candidate.not_engaged,
                random_state=self.config.random_seed,
            )
            > sample
        ):
            return None

        return candidates[n]
