# World Cup Widget modifications

The following are the World Cup specific modifications. These are contained in the `sportsdata.common.sports.WCS` class.

## Redis Data schema

The `RedisAdapter` will be used as the primary way to communicate with Redis. Jobs will require read/write access. Suggest/Widget publication endpoints only really need `read` access.

### Meta Information
key: **sport:wcs:meta**

type: Hash

values:

|name| type | description |
| --- | --- | --- |
| lock | _timestamp_ | initialization lock (Set on NX) |
| meta_updated | _timestamp_ | timestamp for when the last initialization completed |

### Venue information (optional)

key: **sport:wcs:venue:{ _venueId_ }**

type: Hash

values:
| name | type | description |
| --- | --- | --- |
| id  | int | unique venue id |
| name | str | Long form name of the venue |
| city | str | Host city for the venue |
| country | str | ISO3 country code [1] |
| geo | tuple[float] | Lat/Long location information for the venue |

### Team information

This is a reference table for team information. (May include standings?)

key: **sport:wcs:team:{ _teamId_ }**

type: Hash

values:

_See TeamInfo_

### Calendar information

A quicker lookup for game information than using elasticSearch

key: **sport:wcs:calendar**

type: SortedSet

values:

| key | value |
| --- | --- |
| eventKey | UTC timestamp |

### Event fast lookup

key: **sport:wcs:event:{ _eventId_ }**

type: Hash

values:

_See EventInfo_


---
[1] Note that country codes are not provided by the `.../venues` provider endpoint. These will need to be fetched from `.../areas` endpoint.