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
from merino.curated_recommendations.protocol import ExperimentName

INFERRED_LOCAL_EXPERIMENT_NAME = ExperimentName.INFERRED_LOCAL_EXPERIMENT.value
INFERRED_LOCAL_EXPERIMENT_NAME_V2 = ExperimentName.INFERRED_LOCAL_EXPERIMENT_V2.value
INFERRED_LOCAL_EXPERIMENT_NAME_V3 = ExperimentName.INFERRED_LOCAL_EXPERIMENT_V3.value
INFERRED_LOCAL_EXPERIMENT_NAME_V4 = ExperimentName.INFERRED_LOCAL_EXPERIMENT_V4.value

LOCAL_AND_SERVER_V1_MODEL_ID = "local-and-server"
LOCAL_ONLY_V1_MODEL_ID = "local-only"
SERVER_V3_MODEL_ID = "inferred-v3-model"

LOCAL_ONLY_BRANCH_NAME = LOCAL_ONLY_V1_MODEL_ID
LOCAL_AND_SERVER_BRANCH_NAME = LOCAL_AND_SERVER_V1_MODEL_ID
LOCAL_AND_SERVER_V3_BRANCH_NAME = "personalized-stories"
LOCAL_AND_SERVER_V4_BRANCH_NAME = LOCAL_AND_SERVER_V3_BRANCH_NAME

# Ranking based on normalized time zone offset and country
CONTEXTUAL_RANKING_TREATMENT_TZ = "contextual-ranking-content-tz"
# Ranking based on country only
CONTEXTUAL_RANKING_TREATMENT_COUNTRY = "contextual-ranking-content-country"

CTR_TOPIC_MODEL_ID = "ctr_model_topic_1"
CTR_SECTION_MODEL_ID = "ctr_model_section_1"

SUPPORTED_LIVE_MODELS = {SERVER_V3_MODEL_ID}

DEFAULT_PRODUCTION_MODEL_ID = SERVER_V3_MODEL_ID

# Features corresponding to a combination of remaining topics not specified in a feature model
DEFAULT_INTERESTS_KEY = "other"

SPECIAL_FEATURE_CLICK = "clicks"

TOPIC_FOR_SUBTOPIC_SECTION = {
    "movies": Topic.ARTS,
    "tv": Topic.ARTS,
    "music": Topic.ARTS,
    "books": Topic.ARTS,
    "nfl": Topic.SPORTS,
    "nba": Topic.SPORTS,
    "mlb": Topic.SPORTS,
    "nhl": Topic.SPORTS,
    "soccer": Topic.SPORTS,
}

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

BASE_TOPICS_SET = set(BASE_TOPICS)

BASE_SECTIONS_FOR_LOCAL_MODEL = [
    "nfl",
    "nba",
    "mlb",
    "nhl",
    "soccer",
    "tv",
    "movies",
    "music",
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

BASE_SECTIONS_FOR_LOCAL_MODEL_SET = set(BASE_SECTIONS_FOR_LOCAL_MODEL)


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

        category_fields: dict[str, InterestVectorConfig] = {
            a: get_topic(a) for a in BASE_SECTIONS_FOR_LOCAL_MODEL
        }
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

MODEL_P_VALUE_V3 = 0.91
MODEL_Q_VALUE_V3 = 0.030

OFF_THRESH_VALUE = 100

THRESHOLDS_V3_NORMALIZED = [0.3, 0.5, 0.8]

SUBTOPIC_TOPIC_BLEND_RATIO = 0.15

TIME_ZONE_OFFSET_INFERRED_KEY = "timeZoneOffset"


# Creates a limited model based on topics. Topics features are stored with a t_
# in telemetry.
class SuperInferredModel(LocalModelBackend):
    """Class that provides various versions a limited topic models that supports coarse interest vector
    This has with vetted p/q privacy value for the first experiment.
    """

    """
     Based on data analysis these were the most impactful topics from personalization when limited to 5
     The last dimension is a combination of other topics.
    """

    v3_limited_topics = [
        # Top clicked in most popular, though food was dropped for parenting
        Topic.SPORTS.value,
        Topic.ARTS.value,
        Topic.POLITICS.value,
        Topic.PARENTING.value,
        Topic.BUSINESS.value,
        Topic.TECHNOLOGY.value,
        Topic.SCIENCE.value,
        # Time zone is added for 8th private feature
    ]

    v3_small_experiment_topics = {
        Topic.SPORTS.value,
        Topic.PARENTING.value,
        Topic.SCIENCE.value,
    }

    limited_topics_set = set(v3_limited_topics)

    @staticmethod
    def _get_topic(topic: str, thresholds: list[float]) -> InterestVectorConfig:
        return InterestVectorConfig(
            features={f"t_{topic}": 1},
            thresholds=thresholds,
            diff_p=MODEL_P_VALUE_V3,
            diff_q=MODEL_Q_VALUE_V3,
        )

    @staticmethod
    def _get_time_zone() -> InterestVectorConfig:
        """Time zone key has special functionality in Firefox, but we must specifiy privacy and offset here"""
        return InterestVectorConfig(
            features={},
            # TODO - add daylight savings time check so model can switch based on daylight savings time
            # Below are thresholds in 24 offset format so that results are one of current bucketed PST -> EDT
            thresholds=[16.1, 17.1, 18.1],
            diff_p=MODEL_P_VALUE_V3,
            diff_q=MODEL_Q_VALUE_V3,
        )

    @staticmethod
    def _get_section(section_name: str, thresholds: list[float]) -> InterestVectorConfig:
        features = {f"s_{section_name}": 1}
        return InterestVectorConfig(
            features=features,
            thresholds=thresholds,
            diff_p=MODEL_P_VALUE_V3,
            diff_q=MODEL_Q_VALUE_V3,  # Note since these section features are non-private features, p/q are ignored
        )

    def _build_local(
        self, model_id, surface_id, small_experiment=False
    ) -> InferredLocalModel | None:
        model_thresholds = THRESHOLDS_V3_NORMALIZED
        private_features: list[str] | None = None

        limited_topics_set = self.limited_topics_set if not small_experiment else set()
        section_features = {
            a: self._get_section(a, model_thresholds)
            for a in BASE_SECTIONS_FOR_LOCAL_MODEL
            if a not in limited_topics_set
        }

        privacy_overrides = None
        if small_experiment:
            private_features = [TIME_ZONE_OFFSET_INFERRED_KEY]
            # TODO - We could apply privacy overrides here when supported in future Firefox versions
            topic_features = {}
        else:
            topic_features = {
                a: self._get_topic(a, model_thresholds) for a in self.v3_limited_topics
            }
            ## private features are sent to merino have differential privacy applied
            private_features = self.v3_limited_topics + [TIME_ZONE_OFFSET_INFERRED_KEY]

        model_data: ModelData = ModelData(
            model_type=ModelType.CTR,
            rescale=True,
            noise_scale=0.0,
            day_time_weighting=DayTimeWeightingConfig(
                days=[30],
                relative_weight=[1],
            ),
            interest_vector={
                **topic_features,
                TIME_ZONE_OFFSET_INFERRED_KEY: self._get_time_zone(),
                **section_features,
            },
            private_features=private_features,
        )
        return InferredLocalModel(
            model_id=model_id,
            surface_id=surface_id,
            model_data=model_data,
            model_version=0,
            privacy_overrides=privacy_overrides,
        )

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
        if model_id is not None and model_id not in SUPPORTED_LIVE_MODELS:
            ## None here insures we don't parse the wrong model
            ## the local model defintion will be reset by the response
            ## there will be another call to "get" with model_id=None
            ## where the next model is built+returned
            return None

        if model_id is None:  ## this is the "get" call for building the model sent in the response
            ## switch on experiment name, not using util because we have string name instead of request object
            if (
                experiment_name is None  # Default
                or experiment_name == INFERRED_LOCAL_EXPERIMENT_NAME_V4
                or experiment_name == f"optin-{INFERRED_LOCAL_EXPERIMENT_NAME_V4}"
                or experiment_name == INFERRED_LOCAL_EXPERIMENT_NAME_V3
                or experiment_name == f"optin-{INFERRED_LOCAL_EXPERIMENT_NAME_V3}"
            ):
                # We don't have to check for branch here as control won't call inferred code
                return self._build_local(SERVER_V3_MODEL_ID, surface_id)
            else:
                # We are part of an unknown experiment, so we need to tweak privacy.
                return self._build_local(
                    SERVER_V3_MODEL_ID + "_exp", surface_id, small_experiment=True
                )
        # Normally we would pick the model based on model_id here, but we are supporting only one right now
        return self._build_local(SERVER_V3_MODEL_ID, surface_id)
