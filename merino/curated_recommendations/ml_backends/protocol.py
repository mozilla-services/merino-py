"""Protocol and Pydantic models for the Local Model provider backend."""

from enum import Enum
from typing import Protocol
from pydantic import BaseModel


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


class LocalModelBackend(Protocol):
    """Protocol for local model that is applied to New Tab article interactions on the client."""

    def get(self, surface_id: str | None = None) -> InferredLocalModel | None:
        """Fetch local model for the region"""
        ...
