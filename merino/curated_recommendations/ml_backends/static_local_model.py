"""Backup local model for testing and in case of GCS failure"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from merino.curated_recommendations.corpus_backends.protocol import Topic
from merino.curated_recommendations.ml_backends.protocol import (
    InferredLocalModel,
    LocalModelBackend,
    ModelData,
    InterestVectorConfig,
    ModelType,
    DayTimeWeightingConfig,
    PrivacyOverrides,
)
from merino.curated_recommendations.protocol import ExperimentName

INFERRED_LOCAL_EXPERIMENT_NAME = ExperimentName.INFERRED_LOCAL_EXPERIMENT.value
INFERRED_LOCAL_EXPERIMENT_NAME_V2 = ExperimentName.INFERRED_LOCAL_EXPERIMENT_V2.value
INFERRED_LOCAL_EXPERIMENT_NAME_V3 = ExperimentName.INFERRED_LOCAL_EXPERIMENT_V3.value
INFERRED_LOCAL_EXPERIMENT_NAME_V4 = ExperimentName.INFERRED_LOCAL_EXPERIMENT_V4.value

TEST_INFERRED_EXPERIMENT = "test-inferred-experiment"

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
EXPERIMENT_PRODUCTION_MODEL_ID = SERVER_V3_MODEL_ID + "_exp"

# These cause interest vector to have no randomization and should only be used
# when thresholds force a constant ouput
FIXED_VALUE_P = 1.0
FIXED_VALUE_Q = 0.0

# Very high threshold to ensure that the 0 index is always returned
VERY_HIGH_THRESHOLD = 1000.0

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


# See calculation https://colab.research.google.com/drive/1GlEr2TScikP8YLKpAL1sGTawnimD1IyV#scrollTo=KawDDJnjBwIM
# Section March 2026 rollout
MODEL_P_VALUE = 0.92
MODEL_Q_VALUE = 0.0288


OFF_THRESH_VALUE = 100

THRESHOLDS_V3_NORMALIZED = [0.25, 0.46, 0.8]
THRESHOLDS_V3_NON_NORMALIZED = [0.002, 0.008, 0.017]
THRESHOLDS_V3_NON_NORMALIZED_ALL_TOPICS = [0.0001, 0.002, 0.004]

SUBTOPIC_TOPIC_BLEND_RATIO = 0.15

TIME_ZONE_OFFSET_INFERRED_KEY = "timeZoneOffset"

CLICK_RANDOMIZATION_EPSILON_MICRO_FOR_EXPERIMENT = 14700000

SPECIAL_ALL_TOPIC_KEYWOWRD = "all"


class PrivacyOverridesForFivePercentExperimentUS(PrivacyOverrides):
    """Defines privacy overrides, so they can be applied automatically for Merino based experiments to reduce risk of privacy issues"""

    def __init__(self, **data) -> None:
        data.setdefault("iv_in_telemetry", False)
        data.setdefault(
            "random_content_click_probability_epsilon_micro",
            CLICK_RANDOMIZATION_EPSILON_MICRO_FOR_EXPERIMENT,
        )
        data.setdefault(
            "daily_click_event_cap", 2
        )  # Cap of 10 click events per day to reduce risk of outliers
        super().__init__(**data)


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
        Topic.FOOD.value,
        Topic.TECHNOLOGY.value,
        Topic.SCIENCE.value,
        # Time zone is added for 8th private feature
    ]

    # These are the only features supported in a small experiment (in addition to time zone)
    v3_small_experiment_topics = {
        Topic.SPORTS.value,
        Topic.PARENTING.value,
        Topic.SCIENCE.value,
    }

    limited_topics_set = set(v3_limited_topics)

    @staticmethod
    def _get_topic(
        topic: str, thresholds: list[float], disable_feature=False
    ) -> InterestVectorConfig:
        """Return feature for a topic, with a disabled (constant 0 output) feature
        if disabled_feature is True.

        Sometimes for privacy purposes we want to keep the feature in the list for
        interest vector consistency issues, but hard code to 0 for a particual privacy profile,
        such as within an experiment
        """
        if disable_feature:
            return InterestVectorConfig(
                features={f"t_{topic}": 1},
                thresholds=[VERY_HIGH_THRESHOLD for _ in range(len(thresholds))],
                diff_p=FIXED_VALUE_P,
                diff_q=FIXED_VALUE_Q,
            )
        if topic == SPECIAL_ALL_TOPIC_KEYWOWRD:
            return InterestVectorConfig(
                features={f"t_{t}": 1 for t in BASE_TOPICS},
                thresholds=THRESHOLDS_V3_NON_NORMALIZED_ALL_TOPICS,
                diff_p=MODEL_P_VALUE,
                diff_q=MODEL_Q_VALUE,
            )
        return InterestVectorConfig(
            features={f"t_{topic}": 1},
            thresholds=thresholds,
            diff_p=MODEL_P_VALUE,
            diff_q=MODEL_Q_VALUE,
        )

    @staticmethod
    def _get_time_zone() -> InterestVectorConfig:
        """Time zone key has special functionality in Firefox, but we must specifiy threshols here
        based on UTC offset +24 (positive values). These thresholds support the 4 continental US zones
        """
        now: datetime = datetime.now(ZoneInfo("America/Los_Angeles"))
        offset: timedelta = now.utcoffset() or timedelta(0)
        pacific_bucket: float = (offset.total_seconds() / 3600) % 24
        return InterestVectorConfig(
            features={},
            thresholds=[pacific_bucket + 0.1, pacific_bucket + 1.1, pacific_bucket + 2.1],
            diff_p=MODEL_P_VALUE,
            diff_q=MODEL_Q_VALUE,
        )

    @staticmethod
    def _get_section(section_name: str, thresholds: list[float]) -> InterestVectorConfig:
        features = {f"s_{section_name}": 1}
        return InterestVectorConfig(
            features=features,
            thresholds=thresholds,
            diff_p=MODEL_P_VALUE,
            diff_q=MODEL_Q_VALUE,  # Note since these section features are non-private features, p/q are ignored
        )

    def _build_local(
        self, model_id, surface_id, small_experiment=False
    ) -> InferredLocalModel | None:
        model_thresholds = THRESHOLDS_V3_NORMALIZED
        private_features: list[str] | None = None

        section_features = {
            a: self._get_section(a, model_thresholds)
            for a in BASE_SECTIONS_FOR_LOCAL_MODEL
            if a not in self.limited_topics_set
        }

        private_features = self.v3_limited_topics + [TIME_ZONE_OFFSET_INFERRED_KEY]

        if small_experiment:
            topic_features = {
                a: self._get_topic(
                    a, model_thresholds, disable_feature=a not in self.v3_small_experiment_topics
                )
                for a in self.v3_limited_topics
            }
        else:
            topic_features = {
                a: self._get_topic(a, model_thresholds) for a in self.v3_limited_topics
            }

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
        # No privacy overrides until this is implemented in Merino
        privacy_overrides: PrivacyOverrides | None = (
            PrivacyOverridesForFivePercentExperimentUS() if small_experiment else None
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
            ):
                # We don't have to check for branch here as control won't call inferred code
                return self._build_local(SERVER_V3_MODEL_ID, surface_id)
            else:
                return self._build_local(
                    EXPERIMENT_PRODUCTION_MODEL_ID, surface_id, small_experiment=True
                )
        # Normally we would pick the model based on model_id here, but we are supporting only one right now
        return self._build_local(SERVER_V3_MODEL_ID, surface_id)
