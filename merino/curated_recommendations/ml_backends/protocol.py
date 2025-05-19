"""Protocol and Pydantic models for the Local Model provider backend."""

from enum import Enum
from typing import Protocol, Any
from pydantic import BaseModel, ConfigDict


# Define the model type enum
class ModelType(str, Enum):
    CLICKS = "clicks"
    CLICK_IMP_PAIR = "click_impression_pair"


# Interest vector category configuration
class InterestVectorConfig(BaseModel):
    # features that are added together to form the output value
    features: dict[str, float]

    # Threshold ranges for forming a coarse integer value (0, 1, 2, etc.)
    thresholds: list[float]

    # Differential privacy p and q values for unary encoding
    diff_p: float
    diff_q: float


# Top-level model config
class DayTimeWeightingConfig(BaseModel):
    # day ranges and relative weights. Each list must have the same length
    days: list[int]
    relative_weight: list[float]


class ModelData(BaseModel):
    model_type: ModelType
    # Whether to rescale the values based on 1 max value
    rescale: bool
    day_time_weighting: DayTimeWeightingConfig
    # Output key, and inputs for how fields affect it
    interest_vector: dict[str, InterestVectorConfig]


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
