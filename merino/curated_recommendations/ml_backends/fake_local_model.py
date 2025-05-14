"""Backup local model for testing and in case of GCS failure"""

from merino.curated_recommendations.ml_backends.protocol import (
    InferredLocalModel,
    LocalModelBackend,
)

FAKE_MODEL_ID = "fake_model_id"
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

        def get_topic(topic):
            return {
                "features": {f"t_{topic}": 1},
                "thresholds": [0.3, 0.4],
                "diff_p": 0.75,
                "diff_q": 0.25,
            }

        category_fields = {a: get_topic(a) for a in BASE_TOPICS}

        model_data = {
            "model_type": "clicks",
            "rescale": True,
            "day_time_weighting": {
                "days": [3, 14, 45],
                "relative_weight": [1, 1, 1],
            },
            "interest_vector": {
                **category_fields,
                SPECIAL_FEATURE_CLICK: {
                    "features": {"click": 1},
                    "thresholds": [2, 8, 40],
                    "diff_p": 0.9,
                    "diff_q": 0.1,
                },
            },
        }
        return InferredLocalModel(
            model_id=FAKE_MODEL_ID, surface_id=surface_id, model_data=model_data
        )
