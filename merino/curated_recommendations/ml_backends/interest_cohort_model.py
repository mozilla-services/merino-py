"""Torch model that assigns the user to a particular cohort based on the inferred interests."""

import torch
import torch.nn as nn


class InterestCohortModel(nn.Module):
    """Model that assigns the user to a particular cohort based on the inferred interests.
    This model is trained so that more relevant bits are used
    """

    def __init__(
        self,
        num_interest_bits: int = 32,
        num_hidden_interests: int = 16,
        target_cohorts: int = 16,
        num_topics: int = 16,
    ):
        super().__init__()
        self.num_interest_bits = num_interest_bits
        self.target_cohorts = target_cohorts
        self.num_topics = num_topics
        self.num_hidden_interests = num_hidden_interests

        # interests -> cohort probabilities (B, K)
        self.interest_layer = nn.Sequential(
            nn.Linear(num_interest_bits, num_hidden_interests),
            nn.ReLU(),
            nn.Linear(num_hidden_interests, target_cohorts),
            nn.Softmax(dim=-1),
        )

    def forward(self, interests: torch.Tensor) -> torch.Tensor:
        """interests: (B, num_interest_bits)
        returns:   (B, target_cohorts)
        """
        if interests.dim() != 2 or interests.size(1) != self.num_interest_bits:
            raise ValueError(
                f"interests must be (B, {self.num_interest_bits}), got {tuple(interests.shape)}"
            )
        return self.interest_layer(interests)
