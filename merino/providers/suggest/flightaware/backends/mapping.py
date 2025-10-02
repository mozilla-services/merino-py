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


def parsing(query: str) -> str:
    """Parses a query to an identified airline and flight number"""
    query = query.strip().lower()
    idx = query.rfind(" ")
    if idx != "-1":
        name = query[:idx].strip()
        try:
            number = int(query[idx:].strip())
        except:
            return "Bad Number"
    else:
        return "No Number"
    if name.upper() in iata:
        return name.upper() + " " + str(number)
    elif name in name_mapping:
        return name_mapping[name] + " " + str(number)
    elif name.upper() in icao_mapping:
        return icao_mapping[name] + " " + str(number)
    return "Unidentified Airline"

# print(parsing("ac 130"))
# print(parsing("united airlines 101"))
