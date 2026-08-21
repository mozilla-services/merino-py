"""Pydantic model for Yelp suggestions as they should be serialized in the
output JSON.
"""

from pydantic import BaseModel

from merino.jobs.csv_rs_uploader.base import BaseSuggestion

FIELD_SUBJECTS = "subjects"
FIELD_BUSINESS_SUBJECTS = "business-subjects"
FIELD_PRE_MODIFIERS = "pre-modifiers"
FIELD_POST_MODIFIERS = "post-modifiers"
FIELD_LOCATION_MODIFIERS = "location-modifiers"
FIELD_LOCATION_SIGNS = "location-signs"
FIELD_YELP_MODIFIERS = "yelp-modifiers"

# There is a Yelp icon that we manually uploaded to Remote Settings with
# the record ID `icon-yelp-favicon`. It can be internally referenced with
# the ID `yelp-favicon`. Make sure you update this icon ID if you want to
# use a different record ID for the Yelp icon on Remote Settings.
ICON_ID = "yelp-favicon"


class LocationSign(BaseModel):
    """Model for location sign used in Yelp suggestion dataset as they should
    be serialized in the output JSON.
    """

    keyword: str
    needLocation: bool


class Suggestion(BaseSuggestion):
    """Model for Yelp suggestions as they should be serialized in the output
    JSON.
    """

    subjects: list[str]
    businessSubjects: list[str]
    preModifiers: list[str]
    postModifiers: list[str]
    locationSigns: list[LocationSign]
    yelpModifiers: list[str]
    icon: str

    @classmethod
    def csv_to_suggestions(cls, csv_reader) -> list["Suggestion"]:
        """Convert CSV content to Yelp Suggestions."""
        subjects = []
        business_subjects = []
        pre_modifiers = []
        post_modifiers = []
        location_signs = []
        yelp_modifiers = []

        for row in csv_reader:
            subject = row[FIELD_SUBJECTS]
            if subject:
                subjects.append(subject)

            business_subject = row[FIELD_BUSINESS_SUBJECTS]
            if business_subject:
                business_subjects.append(business_subject)

            pre_modifier = row[FIELD_PRE_MODIFIERS]
            if pre_modifier:
                pre_modifiers.append(pre_modifier)

            post_modifier = row[FIELD_POST_MODIFIERS]
            if post_modifier:
                post_modifiers.append(post_modifier)

            location_modifier = row[FIELD_LOCATION_MODIFIERS]
            if location_modifier:
                location_signs.append(LocationSign(keyword=location_modifier, needLocation=False))

            location_sign = row[FIELD_LOCATION_SIGNS]
            if location_sign:
                location_signs.append(LocationSign(keyword=location_sign, needLocation=True))

            yelp_modifier = row[FIELD_YELP_MODIFIERS]
            if yelp_modifier:
                yelp_modifiers.append(yelp_modifier)

        return [
            Suggestion(
                subjects=subjects,
                businessSubjects=business_subjects,
                preModifiers=pre_modifiers,
                postModifiers=post_modifiers,
                locationSigns=location_signs,
                yelpModifiers=yelp_modifiers,
                icon=ICON_ID,
            )
        ]
