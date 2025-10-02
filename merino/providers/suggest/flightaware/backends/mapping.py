import json

# IATA code set
iata = set()

# Name and ICAO mapping : IATA
name_mapping = {}
icao_mapping = {}

with open('airlines.json', 'r') as file:
    data = json.load(file)

for airline in data:
    if airline["active"] == "Y":
        if airline["iata"].isalpha():
            iata.add(airline["iata"])
            name_mapping[airline["name"].lower()] = airline["iata"]
            if airline["icao"].isalpha():
                icao_mapping[airline["icao"]] = airline["iata"]
        elif airline["icao"].isalpha():
            name_mapping[airline["name"].lower()] = airline["icao"]
            icao_mapping[airline["icao"]] = airline["icao"]


def parsing(query: str) -> list:
    """Parses a query to an identified airline and flight number"""
    query = query.strip().lower()
    idx = query.rfind(" ")
    flight_data = []
    if idx != "-1":
        name = query[:idx].strip()
        try:
            number = int(query[idx:].strip())
        except:
            # Bad Number
            return flight_data
    else:
        # No Number
        return flight_data
    if name.upper() in iata:
        flight_data = [name.upper(), number]
    elif name in name_mapping:
        flight_data = [name_mapping[name], number]
    elif name.upper() in icao_mapping:
        flight_data = [icao_mapping[name], number]
    else:
        # Unidentified Airline
        pass
    return flight_data

# print(parsing("ac 130"))
# print(parsing("united airlines 101"))
