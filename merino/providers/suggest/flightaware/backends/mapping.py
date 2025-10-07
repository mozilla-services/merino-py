"""Mapper to convert Name or ICAO to IATA with ICAO as backup"""

import json

# Name : IATA mapping with ICAO as backup
# Optional alias handling is included
name_mapping = {}

# IATA : Name and ICAO : Name mapping
code_mapping = {}

# Note that the mappings cannot be merged due to conflict
# For example "88" is both an airline name (IATA code "47")
# and an IATA code for the airline "All Australia"

with open("merino/providers/suggest/flightaware/backends/airlines.json", "r") as file:
    data = json.load(file)

for airline in data:
    if airline["active"] == "Y":
        if airline["iata"].isalnum():
            name_mapping[airline["name"]] = airline["iata"]
            if (
                airline["alias"] != ""
                and airline["alias"] != "\\N"
                and airline["alias"] not in name_mapping
            ):
                name_mapping[airline["alias"]] = airline["iata"]
            code_mapping[airline["iata"]] = airline["name"]
            if airline["icao"].isalpha():
                code_mapping[airline["icao"]] = airline["name"]
        elif airline["icao"].isalpha():
            name_mapping[airline["name"]] = airline["icao"]
            if (
                airline["alias"] != ""
                and airline["alias"] != "\\N"
                and airline["alias"] not in name_mapping
            ):
                name_mapping[airline["alias"]] = airline["iata"]
            code_mapping[airline["icao"]] = airline["name"]

# print(name_mapping)
# print(code_mapping)
