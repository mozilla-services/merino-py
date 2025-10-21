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

LOCAL_EXPERIMENT_NAME = "optin-new-tab-automated-personalization-local-ranking"
LOCAL_AND_SERVER_V1 = "local-and-server"
LOCAL_ONLY_V1 = "local-only"
LOCAL_ONLY_BRANCH_NAME = LOCAL_ONLY_V1
LOCAL_AND_SERVER_BRANCH_NAME = LOCAL_AND_SERVER_V1

CTR_TOPIC_MODEL_ID = "ctr_model_topic_1"
CTR_SECTION_MODEL_ID = "ctr_model_section_1"

CTR_LIMITED_TOPIC_MODEL_ID_V1_A = "ctr_limited_topic_v1"
CTR_LIMITED_TOPIC_MODEL_ID_V1_B = "ctr_limited_topic_v1_b"
SUPPORTED_LIVE_MODELS = {
    CTR_LIMITED_TOPIC_MODEL_ID_V1_A,
    CTR_LIMITED_TOPIC_MODEL_ID_V1_B,
    LOCAL_AND_SERVER_V1,
    LOCAL_ONLY_V1,
}

DEFAULT_PRODUCTION_MODEL_ID = CTR_LIMITED_TOPIC_MODEL_ID_V1_B

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

    def get(
        self,
        surface_id: str | None = None,
        model_id: str | None = None,
        experiment_name: str | None = None,
        experiment_branch: str | None = None,
    ) -> InferredLocalModel | None:
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


MODEL_P_VALUE_V1 = 0.806
MODEL_Q_VALUE_V1 = 0.030

THRESHOLDS_V1_A = [0.008, 0.016, 0.024]
THRESHOLDS_V1_B = [0.005, 0.010, 0.015]


# Creates a limited model based on topics. Topics features are stored with a t_
# in telemetry.
class SuperTopicModel(LocalModelBackend):  ## TODO normalization
    """Class that provides various versions a limited topic models that supports coarse interest vector
    This has with vetted p/q privacy value for the first experiment.
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

    default_model_id = DEFAULT_PRODUCTION_MODEL_ID

    def get(
        self,
        surface_id: str | None = None,
        model_id: str | None = None,
        experiment_name: str | None = None,
        experiment_branch: str | None = None,
    ) -> InferredLocalModel | None:
        """Fetch local model for the region and optional target experiment branch/name

        If model_id is not none, only return a model of id specified, otherwise return Null
        If model is None, return default model for the surface and experiment.

        A common use case may be to call this function with the model_id to get the model
        information for decoding the interests sent, then calling again with model_id=None
        to return the current default model for future interest calculations.
        """

        def get_topic(topic: str, thresholds: list[float]) -> InterestVectorConfig:
            return InterestVectorConfig(
                features={f"t_{topic}": 1},
                thresholds=thresholds,
                diff_p=MODEL_P_VALUE_V1,
                diff_q=MODEL_Q_VALUE_V1,
            )

        def get_section(section_name: str, thresholds: list[float]) -> InterestVectorConfig:
            return InterestVectorConfig(
                features={f"s_{section_name}": 1},
                thresholds=thresholds,
                diff_p=MODEL_P_VALUE_V1,
                diff_q=MODEL_Q_VALUE_V1,
            )

        if model_id is not None:
            """ If model is specified we only return if supported. """
            if model_id not in SUPPORTED_LIVE_MODELS:
                return None
        model_thresholds = THRESHOLDS_V1_B
        if model_id == CTR_LIMITED_TOPIC_MODEL_ID_V1_A:
            model_thresholds = THRESHOLDS_V1_A
        if model_id is None:
            model_id = CTR_LIMITED_TOPIC_MODEL_ID_V1_B
        category_fields: dict[str, InterestVectorConfig]
        private_features: list[str] | None
        if experiment_name is not None and experiment_name == LOCAL_EXPERIMENT_NAME:
            if experiment_branch == LOCAL_AND_SERVER_BRANCH_NAME:
                ## private features are sent to merino, "private" from differentially private
                private_features = [
                    "sports",
                    "government",
                    "arts",
                    "health",
                    "business",
                    "education-science",
                ]  ## TODO "education-science"?
                model_id = LOCAL_AND_SERVER_V1
            else:  ## includes (experiment_branch == LOCAL_ONLY_BRANCH_NAME)
                ## nothing sent to merino
                private_features = []
                model_id = LOCAL_ONLY_V1
            category_fields = {
                a: get_section(a, model_thresholds) for a in BASE_SECTIONS
            }  ## all sections
        else:
            private_features = None  ## private features null on frontend
            category_fields = {a: get_topic(a, model_thresholds) for a in self.limited_topics}
            # Remainder of topics an interest
            remainder_topic_list = [
                topic for topic in Topic if topic not in self.limited_topics_set
            ]
            category_fields[DEFAULT_INTERESTS_KEY] = InterestVectorConfig(
                features={f"t_{topic_obj.value}": 1 for topic_obj in remainder_topic_list},
                thresholds=model_thresholds,
                diff_p=MODEL_P_VALUE_V1,
                diff_q=MODEL_Q_VALUE_V1,
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
            private_features=private_features,
        )
        return InferredLocalModel(
            model_id=model_id,
            surface_id=surface_id,
            model_data=model_data,
            model_version=0,
        )
