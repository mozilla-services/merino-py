"""Models & enums for SERP categories."""

from enum import Enum


class Category(Enum):
    """Enum of possible SERP categories (interests) for a suggestion."""

    Inconclusive = 0
    Animals = 1
    Arts = 2
    Autos = 3
    Business = 4
    Career = 5
    Education = 6
    Fashion = 7
    Finance = 8
    Food = 9
    Government = 10
    # Disable this per policy consultation
    # Health = 11
    Hobbies = 12
    Home = 13
    News = 14
    RealEstate = 15
    Society = 16
    Sports = 17
    Tech = 18
    Travel = 19
