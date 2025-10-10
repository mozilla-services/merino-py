"""Protocol and Pydantic models for the Local Model provider backend."""

from enum import Enum
from typing import Protocol, cast

import numpy as np
from pydantic import BaseModel

LOCAL_MODEL_MODEL_ID_KEY = "model_id"


# Define the model type enum
class ModelType(str, Enum):
    """Type of model. Indicates source of data, such as whether we are working with clicks or include impressions"""

    CLICKS = "clicks"
    CTR = "ctr"
    CLICK_IMP_PAIR = "click_impression_pair"


# Interest vector category configuration
class InterestVectorConfig(BaseModel):
    """Class that defines the mapping of several article features (that were impressed, clicked etc) to an output feature"""

    # features that are added together to form the output value
    features: dict[str, float]

    # Threshold ranges for forming a coarse integer value (0, 1, 2, etc.)
    thresholds: list[float]

    # Differential privacy p and q values for unary encoding
    diff_p: float
    diff_q: float


# Top-level model config
class DayTimeWeightingConfig(BaseModel):
    """Day ranges and relative weights. 1 is no special weighting. Each list (days and relative_weight) must have the same length"""

    days: list[int]
    relative_weight: list[float]


class ModelData(BaseModel):
    """Data defining a model that maps interactions over many features to an interest vector of smaller number of dimensions"""

    model_type: ModelType
    # Whether to rescale the values based on 1 max value
    rescale: bool
    day_time_weighting: DayTimeWeightingConfig
    # Output key, and inputs for how fields affect it
    interest_vector: dict[str, InterestVectorConfig]
    noise_scale: float


class InferredLocalModel(BaseModel):
    """Class that defines parameters on the local Firefox client for defining an interest vector from interaction
    events
    """

    model_id: str

    # Schema version
    model_version: int
    surface_id: str

    model_data: ModelData

    def get_unary_encoded_index(self, encoded_string: str, support_two: bool = False) -> list[int]:
        """Decode a unary encoded string with differential privacy added.
        Input must be a string containing 0's and 1's representing a one-hot-encoded
        string length representing the 0-indexed possible values. Since randomness may be added
        we can choose to return None if there are multiple 1's.
        The function does not typecheck the string and assume non-"0" values are "1" values

        Returns a list of 1 or 2 integers between 0 and the length of the input string,
        or empty list if all values are 0.

        If support_two is False, then a result is returned if there is exactly one 1 value,
        """
        bin_values = np.frombuffer(encoded_string.encode("ascii"), dtype=np.uint8) - ord("0")
        candidates = np.flatnonzero(bin_values)
        if candidates.size == 1:
            return [int(candidates[0])]
        if support_two and candidates.size == 2:
            return [int(candidates[0]), int(candidates[1])]
        return []

    def model_matches_interests(self, interest_key: float | str | None) -> bool:
        """Return whether a user's inferred interests are created with the correct
        model ID for this model.
        """
        return interest_key is not None and interest_key == self.model_id

    def get_interest_keys(self) -> set[str]:
        """Return set of keys, each representing an interest computed by the model"""
        return set(self.model_data.interest_vector.keys())

    def decode_dp_interests(
        self, dp_values: list[str], interest_key: float | str | None, support_two: bool = True
    ) -> dict[str, float | str]:
        """Decode differentially private (DP) interest values from unary-encoded strings
        into a numeric interest vector.

        This function takes a mapping of inferred interests that may contain
        DP-encoded values (as unary-encoded strings of "0"/"1"). For each entry in
        the model's `interest_vector` configuration, it attempts to decode the
        unary string into an index using `get_unary_encoded_index`. The index is then
        mapped to a threshold value from the model's corresponding features yielding
        a floating-point feature score. Differentially private values are mapped to
        model features based on the dictionary keys sorting order.

        :param interests: User interest vector in differentially private encoding
        :param support_two: Supports two values set due to randomness (return mean as result)
        :returns:
            An updated inferred interests.
        :raises Exception:
            If model IDs do not match, or there is a mismatch in length and format of the
            values
        """

        def interpret_index(index: int) -> float:
            feature_result: float = 0.0
            if index > 0:
                feature_result = ivconfig.thresholds[index - 1]
            return feature_result

        result: dict[str, float | str] = {LOCAL_MODEL_MODEL_ID_KEY: cast(str, interest_key)}
        for idx, (key, ivconfig) in enumerate(self.model_data.interest_vector.items()):
            decoded_values: list[float] = [
                interpret_index(a)
                for a in self.get_unary_encoded_index(dp_values[idx], support_two=support_two)
            ]
            if len(decoded_values) == 1:
                # For n thresholds there are n+1 dimensions in the dp string
                # This is because the 0 index means the values is less than the 0 threshold
                result[key] = decoded_values[0]
            if len(decoded_values) == 2:
                # When there are two 1 values there is a high likelyhood that one of them
                # is correct, so we average just in case
                result[key] = 0.5 * (decoded_values[0] + decoded_values[1])
        return result


class LocalModelBackend(Protocol):
    """Protocol for local model that is applied to New Tab article interactions on the client."""

    def get(self, surface_id: str | None = None, model_id: str | None = None) -> InferredLocalModel | None:
        """Fetch local model for the region"""
        ...
