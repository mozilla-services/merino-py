from merino.curated_recommendations.ml_backends.protocol import InferredLocalModel, LocalModelBackend

FAKE_MODEL_ID = "fake_model_id"
class FakeLocalModel(LocalModelBackend):
    def get(self, surface_id: str | None = None) -> InferredLocalModel | None:
        """Fetch local model for the region """
        SPECIAL_FEATURE_CLICK = "clicks"
        topics = ["arts", "education", "business", "tech", "hobbies", "food", "home", "sports", "travel", "society-parenting",
                  "government"]

        def get_topic(topic):
            return {
                "features": {topic: 1},
                "thresholds": [0.3, 0.4],
                "diff_p": 0.75,
                "diff_q": 0.25,
            }

        category_fields = {a: get_topic(a) for a in topics}

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
        print("RETURNING MODEL ****")
        return InferredLocalModel(model_id=FAKE_MODEL_ID, surface_id=surface_id, model_data=model_data)
