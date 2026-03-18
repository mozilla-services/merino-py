"""Torch model that assigns the user to a particular cohort based on the inferred interests."""

import torch
import torch.nn as nn
from typing import cast

INITIAL_NUM_BITS_PER_INTEREST = 4


class InterestCohortModel(nn.Module):
    """Model that assigns the user to a particular cohort based on the inferred interests.
    This model is trained so that more relevant bits are used
    """

    def __init__(
        self,
        num_interest_bits: int = 32,  # input bits
        num_interests: int = 8,
        num_hidden_interests: int = 16,
        target_cohorts: int = 10,
        num_topics: int = 16,
    ):
        super().__init__()
        self.num_interest_bits = num_interest_bits
        self.target_cohorts = target_cohorts
        self.num_topics = num_topics
        self.num_interests = num_interests
        self.num_hidden_interests = num_hidden_interests
        self.num_internal_bits = self.num_interests * (INITIAL_NUM_BITS_PER_INTEREST + 1)

        # interests -> cohort probabilities (B, K)
        self.interest_layer: nn.Module = nn.Sequential(
            nn.Linear(self.num_internal_bits, num_hidden_interests),
            nn.ReLU(),
            nn.Linear(num_hidden_interests, target_cohorts),
        )

    def forward(self, interests: torch.Tensor) -> torch.Tensor:
        """interests: (B, num_interest_bits)
        returns:   (B, target_cohorts)
        """
        B, L = interests.shape
        grouped_by_interest = interests.view(B, self.num_interests, INITIAL_NUM_BITS_PER_INTEREST)
        all_zero = grouped_by_interest.sum(dim=2) == 0
        extra = all_zero.to(dtype=interests.dtype).unsqueeze(2)
        out_grp = torch.cat([grouped_by_interest, extra], dim=2)  # [B, num_interests, num_bits+1]
        zero_column_added = out_grp.view(B, self.num_internal_bits)
        res = self.interest_layer(zero_column_added)
        return cast(torch.Tensor, res)
