"""Protocol and Pydantic models for the Local Model provider backend."""

from enum import Enum
from typing import Protocol

import numpy as np
from pydantic import BaseModel

LOCAL_MODEL_DB_VALUES_KEY = "values"  # Key to differentially private values
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

    def get_unary_encoded_index(self, encoded_string: str, random_if_uncertain: bool = False) -> int | None:
        """Decode a unary encoded string with differential privacy added.
        Input must be a string containing 0's and 1's representing a one-hot-encoded
        string length representing the 0-indexed possible values. Since randomness may be added
        we can choose to return None if there are multiple 1's.
        The function does not typecheck the string and assume non-"0" values are "1" values

        Returns number between 0 and the length of the string, or None if random_if_uncertain is
        True and more than one values in the string are 1.
        """
        bin_values = np.frombuffer(encoded_string.encode("ascii"), dtype=np.uint8) - ord("0")
        candidates = np.flatnonzero(bin_values)
        if candidates.size == 1:
            return int(candidates[0])
        if random_if_uncertain:
            if candidates.size > 0:
                return int(np.random.choice(candidates))
            else:
                return 0
        return None

    def model_matches_interests(self, interests: dict[str, any]):
        """Return whether a user's inferred interests are created with the correct
        model ID for this model.
        """
        return interests is not None and interests.get(LOCAL_MODEL_MODEL_ID_KEY, None) == self.model_id

    def decode_dp_interests(
            self, interests: dict[str, any], random_if_uncertain: bool = False
    ) -> dict[str, any]:
        """Decode differentially private (DP) interest values from unary-encoded strings
        into a numeric interest vector.

        This function takes a mapping of inferred interests that may contain
        DP-encoded values (as unary-encoded strings of "0"/"1"). For each entry in
        the model's `interest_vector` configuration, it attempts to decode the
        unary string into an index using `get_unary_encoded_index`. The index is then
        mapped to a threshold value from the model's corresponding features yielding
        a floating-point feature score. Differentially private values are mapped to
        model features based on the dictionary keys sorting order.

        :param interests: User if uncertain
        :param random_if_uncertain:
            Whether to randomly select among multiple "1" candidates in a unary
            string. Defaults to False, in which case such features are omitted from the result.
        :returns:
            An updated inferred interests.
        :raises Exception:
            If model IDs do not match, or there is a mismatch in length and format of the
            values
        """
        if not self.model_matches_interests(interests):
            raise Exception("Interests aren't for this model.")
        dp_values: list[str] | None = interests.get(LOCAL_MODEL_DB_VALUES_KEY, None)
        if dp_values is None:
            """ No coarse interests to decode. Simply return what we have which has float values"""
            return interests
        if not isinstance(dp_values, list):
            raise Exception("Missing dp model values")
        if len(self.model_data.interest_vector) != len(dp_values):
            raise "Unexpected number of interests"
        result: dict[str, any] = dict()
        result[LOCAL_MODEL_MODEL_ID_KEY] = interests[LOCAL_MODEL_MODEL_ID_KEY]
        for idx, (key, ivconfig) in enumerate(self.model_data.interest_vector.items()):
            index_interpreted: int | None = self.get_unary_encoded_index(dp_values[idx], random_if_uncertain=random_if_uncertain)
            if index_interpreted is not None:
                # For n thresholds there are n+1 dimensions in the dp string
                # This is because the 0 index means the values is less than the 0 threshold
                feature_result: float = 0.0
                if index_interpreted > 0:
                    feature_result = ivconfig.thresholds[index_interpreted - 1]
                result[key] = feature_result
        return result


class LocalModelBackend(Protocol):
    """Protocol for local model that is applied to New Tab article interactions on the client."""

    def get(self, surface_id: str | None = None) -> InferredLocalModel | None:
        """Fetch local model for the region"""
        ...
