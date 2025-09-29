"""Backup local model for testing and in case of GCS failure"""

from merino.curated_recommendations.corpus_backends.protocol import Topic
from merino.curated_recommendations.ml_backends.protocol import (
    InferredLocalModel,
    LocalModelBackend,
    ModelData,
    InterestVectorConfig,
    ModelType,
    DayTimeWeightingConfig,
)

CTR_TOPIC_MODEL_ID = "ctr_model_topic_1"
CTR_SECTION_MODEL_ID = "ctr_model_section_1"
CTR_LIMITED_TOPIC_MODEL_ID = "ctr_limited_topic_v0"
CTR_LIMITED_TOPIC_MODEL_ID2 = "ctr_limited_topic_v1"

# Features corresponding to a combination of remaining topics not specified in a feature model
DEFAULT_INTERESTS_KEY = "other"

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
class FakeLocalModelTopics(LocalModelBackend):
    """Class that defines sample parameters on the local Firefox client for defining an interest
    vector from interaction events

    Topics are the features of the model. The model is a represetion of users interests.

    Set which model is used at __init__ import
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
            noise_scale=0.002,
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


BASE_SECTIONS = [
    "nfl",
    "nba",
    "mlb",
    "nhl",
    "soccer",
    "tv",
    "movies",
    "music",
    "celebrity news",
    "books",
    "business",
    "career",
    "arts",
    "food",
    "health",
    "home",
    "finance",
    "government",
    "sports",
    "tech",
    "travel",
    "education",
    "hobbies",
    "society-parenting",
    "education-science",
    "society",
]


# Creates a simple model based on sections. Section features are stored with a s_
# in telemetry
class FakeLocalModelSections(LocalModelBackend):
    """Class that defines sample parameters on the local Firefox client for defining an interest
    vector from interaction events

    Sections are the features of the model. The model is a represetion of users interests.

    Set which model is used at __init__ import

    0.002 is about the CTR of users who have clicked at least once
    .0092 is ~99% not to be noise given laplace noise and 0.002 scale
    .0184 is double the first edge
    with these thresholds, the buckets are:
    [probably never clicked, almost certainly clicked, clicked quite a bit]
    """

    def get(self, surface_id: str | None = None) -> InferredLocalModel | None:
        """Fetch local model for the region"""

        def get_topic(topic: str) -> InterestVectorConfig:
            return InterestVectorConfig(
                features={f"s_{topic}": 1},
                thresholds=[0.0092, 0.0184],
                diff_p=0.75,
                diff_q=0.25,
            )

        category_fields: dict[str, InterestVectorConfig] = {a: get_topic(a) for a in BASE_SECTIONS}
        model_data: ModelData = ModelData(
            model_type=ModelType.CTR,
            rescale=False,
            noise_scale=0.002,
            day_time_weighting=DayTimeWeightingConfig(
                days=[3, 14, 45],
                relative_weight=[1, 1, 1],
            ),
            interest_vector=category_fields,
        )

        return InferredLocalModel(
            model_id=CTR_SECTION_MODEL_ID,
            surface_id=surface_id,
            model_data=model_data,
            model_version=0,
        )


V0_MODEL_P_VALUE = 0.806
V0_MODEL_Q_VALUE = 0.030


# Creates a simple model based on sections. Section features are stored with a s_
# in telemetry.
class LimitedTopicV0Model(LocalModelBackend):
    """Class that defines a limited topic model that supports coarse interest vector
    This is the first version for the privacy launch, with vetted p/q privacy values
    Set which model is used at __init__ import
    """

    """
     Based on data analysis these were the most impactful topics from personalization when limited to 6
     However we could in the future benefit from combining HEALTH_FITNESS with SELF_IMPROVEMENT,
     PERSONAL_FINANCE and FOOD. This would free up one additional, possibly SCIENCE or PARENTING
    """
    limited_topics = [
        Topic.SPORTS.value,
        Topic.POLITICS.value,
        Topic.ARTS.value,
        Topic.HEALTH_FITNESS.value,
        Topic.BUSINESS.value,
        Topic.SELF_IMPROVEMENT.value,
    ]

    model_id = CTR_LIMITED_TOPIC_MODEL_ID

    def get(self, surface_id: str | None = None) -> InferredLocalModel | None:
        """Fetch local model for the region
        We could update these thresholds by looking at the percentiles of the CTR
        """

        def get_topic(topic: str) -> InterestVectorConfig:
            return InterestVectorConfig(
                features={f"t_{topic}": 1},
                thresholds=[0.01, 0.02, 0.03]
                if topic is not Topic.SPORTS.value
                else [0.005, 0.008, 0.02],
                diff_p=V0_MODEL_P_VALUE,
                diff_q=V0_MODEL_Q_VALUE,
            )

        category_fields: dict[str, InterestVectorConfig] = {
            a: get_topic(a) for a in self.limited_topics
        }
        model_data: ModelData = ModelData(
            model_type=ModelType.CTR,
            rescale=False,
            noise_scale=0.0,
            day_time_weighting=DayTimeWeightingConfig(
                days=[3, 14, 45],
                relative_weight=[1, 1, 1],
            ),
            interest_vector=category_fields,
        )

        return InferredLocalModel(
            model_id=self.model_id,
            surface_id=surface_id,
            model_data=model_data,
            model_version=0,
        )


# Creates a simple model based on sections. Section features are stored with a s_
# in telemetry.
class LimitedTopicV1Model(LocalModelBackend):
    """Class that defines a limited topic model that supports coarse interest vector
    This is the first version for the privacy launch, with vetted p/q privacy values
    Set which model is used at __init__ import
    """

    """
     Based on data analysis these were the most impactful topics from personalization when limited to 5
     The last dimension is a combination of other topics.
    """
    limited_topics = [
        Topic.SPORTS.value,
        Topic.POLITICS.value,
        Topic.ARTS.value,
        Topic.HEALTH_FITNESS.value,
        Topic.BUSINESS.value,
    ]
    limited_topics_set = set(limited_topics)
    model_id = CTR_LIMITED_TOPIC_MODEL_ID

    def get(self, surface_id: str | None = None) -> InferredLocalModel | None:
        """Fetch local model for the region
        We could update these thresholds by looking at the percentiles of the CTR
        """

        def get_topic(topic: str) -> InterestVectorConfig:
            return InterestVectorConfig(
                features={f"t_{topic}": 1},
                thresholds=[0.008, 0.016, 0.024]
                if topic is not Topic.SPORTS.value
                else [0.005, 0.008, 0.02],
                diff_p=V0_MODEL_P_VALUE,
                diff_q=V0_MODEL_Q_VALUE,
            )

        category_fields: dict[str, InterestVectorConfig] = {
            a: get_topic(a) for a in self.limited_topics
        }
        remainder_topic_list = [topic for topic in Topic if topic not in self.limited_topics_set]
        category_fields[DEFAULT_INTERESTS_KEY] = InterestVectorConfig(
            features={f"t_{topic_obj.value}": 1 for topic_obj in remainder_topic_list},
            thresholds=[0.01, 0.02, 0.03],
            diff_p=V0_MODEL_P_VALUE,
            diff_q=V0_MODEL_Q_VALUE,
        )

        model_data: ModelData = ModelData(
            model_type=ModelType.CTR,
            rescale=False,
            noise_scale=0.0,
            day_time_weighting=DayTimeWeightingConfig(
                days=[3, 14, 45],
                relative_weight=[1, 1, 1],
            ),
            interest_vector=category_fields,
        )

        return InferredLocalModel(
            model_id=self.model_id,
            surface_id=surface_id,
            model_data=model_data,
            model_version=0,
        )
