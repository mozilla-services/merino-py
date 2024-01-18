# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the yelp.py model."""

from merino.jobs.csv_rs_uploader.yelp import (
    FIELD_LOCATION_MODIFIERS,
    FIELD_LOCATION_SIGNS,
    FIELD_POST_MODIFIERS,
    FIELD_PRE_MODIFIERS,
    FIELD_SUBJECTS,
    FIELD_YELP_MODIFIERS,
)
from tests.unit.jobs.csv_rs_uploader.utils import do_csv_test

MODEL_NAME = "yelp"


def test_upload(mocker):
    """Suggestions should be added and validated."""
    do_csv_test(
        mocker=mocker,
        model_name=MODEL_NAME,
        csv_rows=[
            {
                FIELD_SUBJECTS: "subject-1",
                FIELD_PRE_MODIFIERS: "pre-modifier-1",
                FIELD_POST_MODIFIERS: "post-modifier-1",
                FIELD_LOCATION_MODIFIERS: "location-modifier-1",
                FIELD_LOCATION_SIGNS: "location-sign-1",
                FIELD_YELP_MODIFIERS: "yelp-modifier-1",
            },
            {
                FIELD_SUBJECTS: "subject-2",
                FIELD_PRE_MODIFIERS: "pre-modifier-2",
                FIELD_POST_MODIFIERS: "post-modifier-2",
                FIELD_LOCATION_MODIFIERS: "location-modifier-2",
                FIELD_LOCATION_SIGNS: "location-sign-2",
                FIELD_YELP_MODIFIERS: "yelp-modifier-2",
            },
            {
                FIELD_SUBJECTS: "subject-3",
                FIELD_PRE_MODIFIERS: "pre-modifier-3",
                FIELD_POST_MODIFIERS: "post-modifier-3",
                FIELD_LOCATION_MODIFIERS: "location-modifier-3",
                FIELD_LOCATION_SIGNS: "location-sign-3",
                FIELD_YELP_MODIFIERS: "",
            },
            {
                FIELD_SUBJECTS: "subject-4",
                FIELD_PRE_MODIFIERS: "pre-modifier-4",
                FIELD_POST_MODIFIERS: "post-modifier-4",
                FIELD_LOCATION_MODIFIERS: "location-modifier-4",
                FIELD_LOCATION_SIGNS: "",
                FIELD_YELP_MODIFIERS: "",
            },
            {
                FIELD_SUBJECTS: "subject-5",
                FIELD_PRE_MODIFIERS: "pre-modifier-5",
                FIELD_POST_MODIFIERS: "post-modifier-5",
                FIELD_LOCATION_MODIFIERS: "",
                FIELD_LOCATION_SIGNS: "",
                FIELD_YELP_MODIFIERS: "",
            },
            {
                FIELD_SUBJECTS: "subject-6",
                FIELD_PRE_MODIFIERS: "pre-modifier-6",
                FIELD_POST_MODIFIERS: "",
                FIELD_LOCATION_MODIFIERS: "",
                FIELD_LOCATION_SIGNS: "",
                FIELD_YELP_MODIFIERS: "",
            },
            {
                FIELD_SUBJECTS: "subject-7",
                FIELD_PRE_MODIFIERS: "",
                FIELD_POST_MODIFIERS: "",
                FIELD_LOCATION_MODIFIERS: "",
                FIELD_LOCATION_SIGNS: "",
                FIELD_YELP_MODIFIERS: "",
            },
            {
                FIELD_SUBJECTS: "",
                FIELD_PRE_MODIFIERS: "",
                FIELD_POST_MODIFIERS: "",
                FIELD_LOCATION_MODIFIERS: "",
                FIELD_LOCATION_SIGNS: "",
                FIELD_YELP_MODIFIERS: "",
            },
        ],
        expected_suggestions=[
            {
                "subjects": [
                    "subject-1",
                    "subject-2",
                    "subject-3",
                    "subject-4",
                    "subject-5",
                    "subject-6",
                    "subject-7",
                ],
                "preModifiers": [
                    "pre-modifier-1",
                    "pre-modifier-2",
                    "pre-modifier-3",
                    "pre-modifier-4",
                    "pre-modifier-5",
                    "pre-modifier-6",
                ],
                "postModifiers": [
                    "post-modifier-1",
                    "post-modifier-2",
                    "post-modifier-3",
                    "post-modifier-4",
                    "post-modifier-5",
                ],
                "locationSigns": [
                    {
                        "keyword": "location-modifier-1",
                        "needLocation": False,
                    },
                    {
                        "keyword": "location-sign-1",
                        "needLocation": True,
                    },
                    {
                        "keyword": "location-modifier-2",
                        "needLocation": False,
                    },
                    {
                        "keyword": "location-sign-2",
                        "needLocation": True,
                    },
                    {
                        "keyword": "location-modifier-3",
                        "needLocation": False,
                    },
                    {
                        "keyword": "location-sign-3",
                        "needLocation": True,
                    },
                    {
                        "keyword": "location-modifier-4",
                        "needLocation": False,
                    },
                ],
                "yelpModifiers": [
                    "yelp-modifier-1",
                    "yelp-modifier-2",
                ],
            }
        ],
    )
