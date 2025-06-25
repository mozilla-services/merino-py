"""Backup local model for testing and in case of GCS failure"""

from merino.curated_recommendations.ml_backends.protocol import (
    InferredLocalModel,
    LocalModelBackend,
    ModelData,
    InterestVectorConfig,
    ModelType,
    DayTimeWeightingConfig,
)

CTR_TOPIC_MODEL_ID = "ctr_model_topic_1"
SPECIAL_FEATURE_CLICK = "clicks"

BASE_TOPICS = [
    "arts",
    "education",
    "hobbies",
    "society-parenting",
    "business",
    "education-science",
    "finance",
    "food",
    "government",
    "health",
    "home",
    "society",
    "sports",
    "tech",
    "travel",
]


# Creates a simple model based on topics. Topic features are stored with a t_
# in telemetry
class FakeLocalModel(LocalModelBackend):
    """Class that defines sample parameters on the local Firefox client for defining an interest
    vector from interaction events
    """

    def get(self, surface_id: str | None = None) -> InferredLocalModel | None:
        """Fetch local model for the region"""

        def get_topic(topic: str) -> InterestVectorConfig:
            return InterestVectorConfig(
                features={f"t_{topic}": 1},
                thresholds=[0.3, 0.4],
                diff_p=0.75,
                diff_q=0.25,
            )

        category_fields: dict[str, InterestVectorConfig] = {a: get_topic(a) for a in BASE_TOPICS}
        model_data: ModelData = ModelData(
            model_type=ModelType.CTR,
            rescale=False,
            day_time_weighting=DayTimeWeightingConfig(
                days=[3, 14, 45],
                relative_weight=[1, 1, 1],
            ),
            interest_vector=category_fields,
        )

        return InferredLocalModel(
            model_id=CTR_TOPIC_MODEL_ID,
            surface_id=surface_id,
            model_data=model_data,
            model_version=0,
        )
