import json

# Maps ID : Airline JSON data
id_mapping = {}

# Maps Name, IATA and ICAO codes : ID
name_mapping = {}
iata_mapping = {}
icao_mapping = {}

with open('airlines.json', 'r') as file:
    data = json.load(file)

for airline in data:
    id_mapping[airline["id"]] = airline
    name_mapping[airline["name"].lower()] = airline["id"]
    if airline["iata"].isalpha():
        iata_mapping[airline["iata"].lower()] = airline["id"]
    if airline["icao"].isalpha():
        icao_mapping[airline["icao"].lower()] = airline["id"]

def parsing(query: str) -> list:
    """Parses a query to an identified airline and flight number"""
    query = query.strip().lower()
    idx = query.rfind(" ")
    flight_data = []
    if idx != "-1":
        name = query[:idx].strip()
        # print(name)
        try:
            number = int(query[idx:].strip())
            # print(number)
        except:
            # print("bad number")
            return flight_data
    else:
        # print("no number")
        return flight_data
    if name in name_mapping:
        flight_data = [id_mapping[name_mapping[name]], number]
    elif name in iata_mapping:
        flight_data = [id_mapping[iata_mapping[name]], number]
    elif name in icao_mapping:
        flight_data = [id_mapping[icao_mapping[name]], number]
    if not flight_data:
        # print("unidentified airline")
        pass
    return flight_data

# print(parsing("ac 130"))
# print(parsing("united airlines 101"))
