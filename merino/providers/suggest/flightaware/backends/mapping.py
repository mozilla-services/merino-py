"""Mapper to convert Name or ICAO to IATA with ICAO as backup"""

import json

# Name : IATA mapping with ICAO as backup
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
            name_mapping[airline["name"].lower()] = airline["iata"]
            if (
                airline["alias"] != ""
                and airline["alias"] != "\\N"
                and airline["alias"].lower() not in name_mapping
            ):
                name_mapping[airline["alias"].lower()] = airline["iata"]
            code_mapping[airline["iata"]] = airline["name"].lower()
            if airline["icao"].isalpha():
                code_mapping[airline["icao"]] = airline["name"].lower()
        elif airline["icao"].isalpha():
            name_mapping[airline["name"].lower()] = airline["icao"]
            if (
                airline["alias"] != ""
                and airline["alias"] != "\\N"
                and airline["alias"].lower() not in name_mapping
            ):
                name_mapping[airline["alias"].lower()] = airline["iata"]
            code_mapping[airline["icao"]] = airline["name"].lower()

# print(name_mapping)
# print(code_mapping)

valid_airline_codes = set()
for code in code_mapping:
    valid_airline_codes.add(code)

print(valid_airline_codes)
