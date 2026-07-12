"""
Auto-generated Pydantic models for alltrails's MCP. Supported tools are:

Example BoundMCPAgentConfig (JSON) for this provider:
 {
   "server": {
     "type": "http",
     "url": "https://www.alltrails.com/mcp"
   },
   "tools": [
     {
       "name": "find_trails_near_location",
       "input_class_name": "rustic_ai.mcp.connectors.alltrails.FindTrailsNearLocationInput",
       "description": "Find hiking, running, biking, backpacking or other trails for outdoor activities near a set of coordinates within an optional specified maximum radius (meters).\n\nUse this tool when the user:\n* Requests trails near a specific point of interest or landmark.\n* Requests trails near a named location within a specified radius or accessible within a specified time constraint.\n* Provides specific latitude and longitude coordinates.\n\nFor most named places, use the \"search within bounding box\" tool if possible. Use this tool as a fallback when the bounding box of the named place is unknown.\n\nUsers can specify filters related to appropriate activities, attractions, suitability, and more. Numeric range filters related to distance, elevation, and length are also available. These filter values MUST be specified in meters.\n\nIn the response, length and distance values are returned both in meters and imperial units. These MUST be displayed to the user in the units most appropriate for the user's locale, e.g. feet or miles for US English users.\n"
     },
     {
       "name": "find_trails_within_bounds",
       "input_class_name": "rustic_ai.mcp.connectors.alltrails.FindTrailsWithinBoundsInput",
       "description": "Find hiking, running, biking, backpacking or other trails for outdoor activities within a specified bounding box defined by southwest and northeast coordinates.\n\nUse this tool when the user:\n* Requests trails within specific geographic boundaries or coordinates.\n* Requests trails near a named geographic or political place, such as a continent, country, state, province, region, city, town, or neighborhood and you know the bounding box for that place.\n* Requests trails within a national, state or local park or other protected area and you know the bounding box for that park.\n\nIf the bounding box for the named place is not known, use the \"find trails near a location\" tool instead to find trails around a center point.\n\nUsers can specify filters related to appropriate activities, attractions, suitability, and more. Numeric range filters related to distance, elevation, and length are also available. These filter values MUST be specified in meters.\n\nIn the response, length and distance values are returned both in meters and imperial units. These MUST be displayed to the user in the units most appropriate for the user's locale, e.g. feet or miles for US English users.\n"
     },
     {
       "name": "search_trails_by_name",
       "input_class_name": "rustic_ai.mcp.connectors.alltrails.SearchTrailsByNameInput",
       "description": "Search for hiking, running, biking, backpacking or other trails by full or partial name match.\n\nUse this tool when the user:\n* Requests a specific trail by name (e.g., \"Avalanche Lake Trail\", \"Half Dome\")\n* Searches for trails with specific keywords in the name\n\nThe search can biased towards results near the provided coordinates if they are provided explicitly or available from the request metadata.\n\nIf there is a clear match to the user's query, the model should automatically make a subsequent call to the `get_trail_details` tool to present the user with complete details for the matching trail.\n\nIn the response, length and distance values are returned both in meters and imperial units. These MUST be displayed to the user in the units most appropriate for the user's locale, e.g. feet or miles for US English users.\n"
     },
     {
       "name": "get_trail_details",
       "input_class_name": "rustic_ai.mcp.connectors.alltrails.GetTrailDetailsInput",
       "description": "Find detailed information about a trail from AllTrails.\n\nGet descriptive overviews and specific accessibility information. Includes structured data about suitable activities, and feature highlights along the trail.\n\nGet stats about the trail geography and length, and stats about associated user-generated content.\n\nIn the response, length and distance values are returned both in meters and imperial units. These MUST be displayed to the user in the units most appropriate for the user's locale, e.g. feet or miles for US English users.\n\nRecent reviews are summarized in the `review_summary` field. If the user wants information that might be found in specific reviews, direct the user to the AllTrails web URL for the trail.\n"
     },
     {
       "name": "get_trail_weather_overview",
       "input_class_name": "rustic_ai.mcp.connectors.alltrails.GetTrailWeatherOverviewInput",
       "description": "Get 7-day forecast for a trail at its trailhead, including high/low temperatures.\n\nFor more detailed weather information, including current conditions, sunrise/sunset times, and weather alerts, direct the user to the AllTrails web URL for the trail (available in the `get_trail_details` tool response).\n"
     }
   ]
 }

"""  # noqa

from enum import Enum
from typing import Annotated, Optional

from pydantic import BaseModel, Field, RootModel


class MinRating(RootModel[int]):
    root: Annotated[
        int,
        Field(
            description=(
                "The minimum rating of the trail from 0 to 5. This filter can be used to find trails that have a"
                " certain minimum rating. For example, if you want to find trails that have a rating of at least 4"
                " stars, you would use the `minRating` filter with `min: 4` as the value."
            ),
            ge=1,
            le=5,
            title="Min Rating",
        ),
    ]


class ElevationGain(BaseModel):
    """
    The elevation gain of the trail in meters. This filter can be used to find trails that are within a certain
    elevation gain range. For example, if you want to find trails that have an elevation gain of between 500 and 1000
    meters, you would use the `elevationGain` filter with `min: 500` and `max: 1000` as values. IMPORTANT: If the
    user specifies elevation gain in feet (ft), convert to meters using the conversion factor of 1 foot = 0.3048
    meters. For example: '1000 ft elevation gain' → 304.8 meters, '2000-3000 ft elevation gain' → 609.6-914.4 meters,
    'trails with 500 ft of climbing' → 152.4 meters. Always convert feet to meters before setting the filter values.
    """

    min: Annotated[float, Field(description="Minimum value for the range", title="Min")]
    max: Annotated[float, Field(description="Maximum value for the range", title="Max")]


class HighestPoint(BaseModel):
    """
    The highest point on the trail in meters. This filter can be used to find trails that are within a certain
    elevation range. For example, if you want to find trails that are between 1000 and 2000 meters high,
    you would use the `highestPoint` filter with `min: 1000` and `max: 2000` as values.
    """

    min: Annotated[float, Field(description="Minimum value for the range", title="Min")]
    max: Annotated[float, Field(description="Maximum value for the range", title="Max")]


class Length(BaseModel):
    """
    The length of the trail in meters. This filter can be used to find trails that are within a certain distance
    range. For example, if you want to find trails that are between 5 and 10 kilometers long, you would use the
    `length` filter with `min: 5000` and `max: 10000` as values.
    """

    min: Annotated[float, Field(description="Minimum value for the range", title="Min")]
    max: Annotated[float, Field(description="Maximum value for the range", title="Max")]


class Duration(BaseModel):
    """
    Estimated time to complete the trail in minutes. This filter can be used to find trails that are within a certain
    duration range. For example, if you want to find trails that take between 1 and 2 hours to complete,
    you would use the `duration` filter with `min: 60` and `max: 120` as values.
    """

    min: Annotated[float, Field(description="Minimum value for the range", title="Min")]
    max: Annotated[float, Field(description="Maximum value for the range", title="Max")]


class DifficultyEnum(Enum):
    EASY = "easy"
    MODERATE = "moderate"
    HARD = "hard"


class ActivityEnum(Enum):
    BIRDING = "birding"
    CAMPING = "camping"
    CROSS_COUNTRY_SKIING = "cross-country-skiing"
    FISHING = "fishing"
    HIKING = "hiking"
    MOUNTAIN_BIKING = "mountain-biking"
    OFF_ROAD_DRIVING = "off-road-driving"
    ROAD_BIKING = "road-biking"
    ROCK_CLIMBING = "rock-climbing"
    SCENIC_DRIVING = "scenic-driving"
    SKIING = "skiing"
    SNOWSHOEING = "snowshoeing"
    TRAIL_RUNNING = "trail-running"
    WALKING = "walking"
    HORSEBACK_RIDING = "horseback-riding"
    BACKPACKING = "backpacking"
    PADDLE_SPORTS = "paddle-sports"
    BIKE_TOURING = "bike-touring"
    VIA_FERRATA = "via-ferrata"


class Attraction(Enum):
    BEACH = "beach"
    CAVE = "cave"
    FOREST = "forest"
    LAKE = "lake"
    HOT_SPRINGS = "hot-springs"
    RIVER = "river"
    VIEWS = "views"
    WATERFALL = "waterfall"
    WILD_FLOWERS = "wild-flowers"
    WILDLIFE = "wildlife"
    RAILS_TRAILS = "rails-trails"
    CITY_WALK = "city-walk"
    HISTORIC_SITE = "historic-site"
    PUB_CRAWL = "pub-crawl"
    EVENT = "event"


class SuitabilityEnum(Enum):
    DOGS = "dogs"
    DOGS_LEASH = "dogs-leash"
    DOGS_NO = "dogs-no"
    KIDS = "kids"
    ADA = "ada"
    STROLLERS = "strollers"
    PAVED = "paved"
    PARTIALLY_PAVED = "partially-paved"


class RouteTypeEnum(Enum):
    O = "O"  # noqa E741
    L = "L"
    P = "P"


class TrailTrafficEnum(Enum):
    LIGHT = "light"
    MODERATE = "moderate"
    HEAVY = "heavy"


class Filters(BaseModel):
    """
    Search filters to apply
    """

    min_rating: Annotated[
        Optional[MinRating],
        Field(
            description=(
                "The minimum rating of the trail from 0 to 5. This filter can be used to find trails that have a"
                " certain minimum rating. For example, if you want to find trails that have a rating of at least 4"
                " stars, you would use the `minRating` filter with `min: 4` as the value."
            ),
            title="Min Rating",
        ),
    ] = None
    elevation_gain: Annotated[
        Optional[ElevationGain],
        Field(
            description=(
                "The elevation gain of the trail in meters. This filter can be used to find trails that are within a"
                " certain elevation gain range. For example, if you want to find trails that have an elevation gain of"
                " between 500 and 1000 meters, you would use the `elevationGain` filter with `min: 500` and `max: 1000`"
                " as values. IMPORTANT: If the user specifies elevation gain in feet (ft), convert to meters using the"
                " conversion factor of 1 foot = 0.3048 meters. For example: '1000 ft elevation gain' → 304.8 meters,"
                " '2000-3000 ft elevation gain' → 609.6-914.4 meters, 'trails with 500 ft of climbing' → 152.4 meters."
                " Always convert feet to meters before setting the filter values."
            )
        ),
    ] = None
    highest_point: Annotated[
        Optional[HighestPoint],
        Field(
            description=(
                "The highest point on the trail in meters. This filter can be used to find trails that are within a"
                " certain elevation range. For example, if you want to find trails that are between 1000 and 2000"
                " meters high, you would use the `highestPoint` filter with `min: 1000` and `max: 2000` as values."
            )
        ),
    ] = None
    length: Annotated[
        Optional[Length],
        Field(
            description=(
                "The length of the trail in meters. This filter can be used to find trails that are within a certain"
                " distance range. For example, if you want to find trails that are between 5 and 10 kilometers long,"
                " you would use the `length` filter with `min: 5000` and `max: 10000` as values."
            )
        ),
    ] = None
    duration: Annotated[
        Optional[Duration],
        Field(
            description=(
                "Estimated time to complete the trail in minutes. This filter can be used to find trails that are"
                " within a certain duration range. For example, if you want to find trails that take between 1 and 2"
                " hours to complete, you would use the `duration` filter with `min: 60` and `max: 120` as values."
            )
        ),
    ] = None
    difficulty: Annotated[
        Optional[list[DifficultyEnum]],
        Field(
            description=(
                "The difficulty level of the trail. Union filter. There should be no duplicates in the difficulty"
                " array."
            ),
            title="Difficulty",
        ),
    ] = None
    activity: Annotated[
        Optional[list[ActivityEnum]],
        Field(
            description=(
                "The type of activity that can be done on the trail. Intersection filter. For example, if you want to"
                " find trails that are suitable for both hiking and biking, you would use the `activity` filter with"
                " both `hiking` and `biking` as values. There should be no duplicates in the activity array. Activity"
                " types include: birding (Birdwatching), camping (staying overnight), off-road-driving (4x4 vehicles),"
                " via-ferrata (climbing with fixed anchors), paddle-sports (kayaking, canoeing, paddleboarding),"
                " scenic-driving (beautiful scenic routes)."
            ),
            title="Activity",
        ),
    ] = None
    attractions: Annotated[
        Optional[list[Attraction]],
        Field(
            description=(
                "The type of attraction that can be found on the trail. Intersection filter. There should be no"
                " duplicates in the attractions array. Attraction types include: CityWalk (urban trails with city"
                " features), HistoricSite (historic sites and landmarks), PubCrawl (urban trails featuring pubs and"
                " breweries), Event (trails created for specific events like marathons), RailsTrails (converted railway"
                " lines, often flat and straight), Views (scenic views of natural features), Waterfall (trails"
                " featuring waterfalls), WildFlowers (trails with wildflowers - no guarantee of bloom timing), Wildlife"
                " (trails where wildlife can be seen - no guarantee of sightings)."
            ),
            title="Attractions",
        ),
    ] = None
    suitability: Annotated[
        Optional[list[SuitabilityEnum]],
        Field(
            description=(
                "The type of suitability that can be found on the trail. Intersection filter. For example, if you want"
                " to find trails that are suitable for both dogs and kids, you would use the `suitability` filter with"
                " both `dogs` and `kids` as values. There should be no duplicates in the suitability array. Suitability"
                " types include: Ada (Americans with Disabilities Act compliant, accessible to people with"
                " disabilities), Dogs (dogs allowed), DogsLeash (dogs allowed but must be leashed), DogsNo (dogs not"
                " allowed), Strollers (suitable for strollers), Paved (paved trail), PartiallyPaved (partially paved"
                " trail)."
            ),
            title="Suitability",
        ),
    ] = None
    route_type: Annotated[
        Optional[list[RouteTypeEnum]],
        Field(
            description=(
                "The type of the route. Union filter. There should be no duplicates in the route type array. Route"
                " types: O (Out and back route - goes to a point and returns to start), L (Loop route - starts and ends"
                " at the same point), P (Point to point route - starts at one point and ends at another)."
            ),
            title="Route Type",
        ),
    ] = None
    trail_traffic: Annotated[
        Optional[list[TrailTrafficEnum]],
        Field(
            description=(
                "The amount of traffic on the trail. Union filter. This is an average, an approximation, drawn from"
                " internal activity tracking data. It is not a guarantee of how many people will be on the trail at any"
                " given time. Traffic levels: light (light traffic), moderate (moderate traffic), heavy (heavy"
                " traffic)."
            ),
            title="Trail Traffic",
        ),
    ] = None


class Sort(Enum):
    """

    Ability to specify a sorting option.

    The default is NONE. CRITICAL: Only extract sort if the query contains EXPLICIT sort keywords:
    - "best trails", "top trails" → most_popular
    - "closest trails", "nearest trails" → closest
    - "new trails", "recently added" → newly_added


    Only include a sort option if the user's query explicitly indicates a particular sort order.
    If no sort preference is indicated, omit the `sort` property entirely.

    Available sort options:
    - `closest`: Sort by distance from the user's location. Use when the query asks for
    "closest trails" or "trails nearest to" a location.
    - `most_popular`: Sort by overall popularity.
    - `newly_added`: Sort by date added. Use for queries like "new hiking trails".
    - `seasonal`: Sort by popularity at the current time of year. Use when the query asks for trails
    "at this time of year", "this season", "right now", or similar seasonal phrasing.
    - `month_1` through `month_12`: Sort by popularity in a specific month.
    Use when the query mentions a specific month, e.g., "hiking trails in July" → `month_7`.

    """

    SEASONAL = "seasonal"
    CLOSEST = "closest"
    NEWLY_ADDED = "newly_added"
    MONTH_1 = "month_1"
    MONTH_2 = "month_2"
    MONTH_3 = "month_3"
    MONTH_4 = "month_4"
    MONTH_5 = "month_5"
    MONTH_6 = "month_6"
    MONTH_7 = "month_7"
    MONTH_8 = "month_8"
    MONTH_9 = "month_9"
    MONTH_10 = "month_10"
    MONTH_11 = "month_11"
    MONTH_12 = "month_12"
    MOST_POPULAR = "most_popular"


class Locale(RootModel[str]):
    root: Annotated[
        str,
        Field(
            description=(
                "A BCP 47 locale string (e.g. 'en-US', 'es-ES', 'de-DE'). Should be set to the user's device/browser"
                " locale or the language of the current conversation. Used for localizing trail names and descriptions,"
                " difficulty labels, and URLs. Falls back to request metadata if not provided."
            ),
            pattern="^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$",
            title="Locale",
        ),
    ]


class MaxRadiusMeters(RootModel[int]):
    root: Annotated[
        int,
        Field(
            description=(
                "Maximum search radius in meters. \n\nSpecify this value if the user:\n* Indicates they are looking for"
                " nearby trails within a specific distance.\n* Mentions a specific distance around a named location\n*"
                " Mentions a time constraint to reach a location. If the user mentions a time constraint, but does not"
                " mention the mode of transport, assume they are traveling by car. Generate the maximum radius based on"
                " a typical travel speed for the mode of transport.\n* Requests a point of interest or landmark."
                " Generate an appropriate maximum radius between 1000 and 5000 meters.\n* If a bounding box is unknown"
                ' for a named location. (If a bounding box is known, use the "search within bounding box" tool'
                " instead.) Supply this value to ensure the search is performed within a reasonable area for the kind"
                " of location the user is referring to. Example values:\n  * country: 500000m radius\n  *"
                " state/province/official region: 200000m radius\n  * county/administrative area/unofficial region:"
                " 25000m radius\n  * city/town: 10000m radius\n  * neighborhood/district: 2000m radius\n"
            ),
            ge=1,
            title="Max Radius Meters",
        ),
    ]


class Input(BaseModel):
    filters: Annotated[Optional[Filters], Field(description="Search filters to apply")] = None
    limit: Annotated[Optional[int], Field(description="Maximum number of results", ge=1, le=20, title="Limit")] = 20
    sort: Annotated[
        Optional[Sort],
        Field(
            description=(
                "\nAbility to specify a sorting option.\n\nThe default is NONE. CRITICAL: Only extract sort if the"
                ' query contains EXPLICIT sort keywords:\n- "best trails", "top trails" → most_popular\n- "closest'
                ' trails", "nearest trails" → closest\n- "new trails", "recently added" → newly_added\n\n\nOnly include'
                " a sort option if the user's query explicitly indicates a particular sort order.\nIf no sort"
                " preference is indicated, omit the `sort` property entirely.\n\nAvailable sort options:\n- `closest`:"
                ' Sort by distance from the user\'s location. Use when the query asks for\n"closest trails" or "trails'
                ' nearest to" a location.\n- `most_popular`: Sort by overall popularity.\n- `newly_added`: Sort by date'
                ' added. Use for queries like "new hiking trails".\n- `seasonal`: Sort by popularity at the current'
                ' time of year. Use when the query asks for trails\n"at this time of year", "this season", "right now",'
                " or similar seasonal phrasing.\n- `month_1` through `month_12`: Sort by popularity in a specific"
                ' month.\nUse when the query mentions a specific month, e.g., "hiking trails in July" → `month_7`.\n'
            ),
            title="Sort",
        ),
    ] = None
    locale: Annotated[
        Optional[Locale],
        Field(
            description=(
                "A BCP 47 locale string (e.g. 'en-US', 'es-ES', 'de-DE'). Should be set to the user's device/browser"
                " locale or the language of the current conversation. Used for localizing trail names and descriptions,"
                " difficulty labels, and URLs. Falls back to request metadata if not provided."
            ),
            title="Locale",
        ),
    ] = None
    latitude: Annotated[float, Field(description="Latitude in decimal degrees", title="Latitude")]
    longitude: Annotated[float, Field(description="Longitude in decimal degrees", title="Longitude")]
    max_radius_meters: Annotated[
        Optional[MaxRadiusMeters],
        Field(
            description=(
                "Maximum search radius in meters. \n\nSpecify this value if the user:\n* Indicates they are looking for"
                " nearby trails within a specific distance.\n* Mentions a specific distance around a named location\n*"
                " Mentions a time constraint to reach a location. If the user mentions a time constraint, but does not"
                " mention the mode of transport, assume they are traveling by car. Generate the maximum radius based on"
                " a typical travel speed for the mode of transport.\n* Requests a point of interest or landmark."
                " Generate an appropriate maximum radius between 1000 and 5000 meters.\n* If a bounding box is unknown"
                ' for a named location. (If a bounding box is known, use the "search within bounding box" tool'
                " instead.) Supply this value to ensure the search is performed within a reasonable area for the kind"
                " of location the user is referring to. Example values:\n  * country: 500000m radius\n  *"
                " state/province/official region: 200000m radius\n  * county/administrative area/unofficial region:"
                " 25000m radius\n  * city/town: 10000m radius\n  * neighborhood/district: 2000m radius\n"
            ),
            title="Max Radius Meters",
        ),
    ] = None


class FindTrailsNearLocationInput(BaseModel):
    input: Annotated[Input, Field(title="TrailCenterSearchInput")]


class Filters1(BaseModel):
    """
    Search filters to apply
    """

    min_rating: Annotated[
        Optional[MinRating],
        Field(
            description=(
                "The minimum rating of the trail from 0 to 5. This filter can be used to find trails that have a"
                " certain minimum rating. For example, if you want to find trails that have a rating of at least 4"
                " stars, you would use the `minRating` filter with `min: 4` as the value."
            ),
            title="Min Rating",
        ),
    ] = None
    elevation_gain: Annotated[
        Optional[ElevationGain],
        Field(
            description=(
                "The elevation gain of the trail in meters. This filter can be used to find trails that are within a"
                " certain elevation gain range. For example, if you want to find trails that have an elevation gain of"
                " between 500 and 1000 meters, you would use the `elevationGain` filter with `min: 500` and `max: 1000`"
                " as values. IMPORTANT: If the user specifies elevation gain in feet (ft), convert to meters using the"
                " conversion factor of 1 foot = 0.3048 meters. For example: '1000 ft elevation gain' → 304.8 meters,"
                " '2000-3000 ft elevation gain' → 609.6-914.4 meters, 'trails with 500 ft of climbing' → 152.4 meters."
                " Always convert feet to meters before setting the filter values."
            )
        ),
    ] = None
    highest_point: Annotated[
        Optional[HighestPoint],
        Field(
            description=(
                "The highest point on the trail in meters. This filter can be used to find trails that are within a"
                " certain elevation range. For example, if you want to find trails that are between 1000 and 2000"
                " meters high, you would use the `highestPoint` filter with `min: 1000` and `max: 2000` as values."
            )
        ),
    ] = None
    length: Annotated[
        Optional[Length],
        Field(
            description=(
                "The length of the trail in meters. This filter can be used to find trails that are within a certain"
                " distance range. For example, if you want to find trails that are between 5 and 10 kilometers long,"
                " you would use the `length` filter with `min: 5000` and `max: 10000` as values."
            )
        ),
    ] = None
    duration: Annotated[
        Optional[Duration],
        Field(
            description=(
                "Estimated time to complete the trail in minutes. This filter can be used to find trails that are"
                " within a certain duration range. For example, if you want to find trails that take between 1 and 2"
                " hours to complete, you would use the `duration` filter with `min: 60` and `max: 120` as values."
            )
        ),
    ] = None
    difficulty: Annotated[
        Optional[list[DifficultyEnum]],
        Field(
            description=(
                "The difficulty level of the trail. Union filter. There should be no duplicates in the difficulty"
                " array."
            ),
            title="Difficulty",
        ),
    ] = None
    activity: Annotated[
        Optional[list[ActivityEnum]],
        Field(
            description=(
                "The type of activity that can be done on the trail. Intersection filter. For example, if you want to"
                " find trails that are suitable for both hiking and biking, you would use the `activity` filter with"
                " both `hiking` and `biking` as values. There should be no duplicates in the activity array. Activity"
                " types include: birding (Birdwatching), camping (staying overnight), off-road-driving (4x4 vehicles),"
                " via-ferrata (climbing with fixed anchors), paddle-sports (kayaking, canoeing, paddleboarding),"
                " scenic-driving (beautiful scenic routes)."
            ),
            title="Activity",
        ),
    ] = None
    attractions: Annotated[
        Optional[list[Attraction]],
        Field(
            description=(
                "The type of attraction that can be found on the trail. Intersection filter. There should be no"
                " duplicates in the attractions array. Attraction types include: CityWalk (urban trails with city"
                " features), HistoricSite (historic sites and landmarks), PubCrawl (urban trails featuring pubs and"
                " breweries), Event (trails created for specific events like marathons), RailsTrails (converted railway"
                " lines, often flat and straight), Views (scenic views of natural features), Waterfall (trails"
                " featuring waterfalls), WildFlowers (trails with wildflowers - no guarantee of bloom timing), Wildlife"
                " (trails where wildlife can be seen - no guarantee of sightings)."
            ),
            title="Attractions",
        ),
    ] = None
    suitability: Annotated[
        Optional[list[SuitabilityEnum]],
        Field(
            description=(
                "The type of suitability that can be found on the trail. Intersection filter. For example, if you want"
                " to find trails that are suitable for both dogs and kids, you would use the `suitability` filter with"
                " both `dogs` and `kids` as values. There should be no duplicates in the suitability array. Suitability"
                " types include: Ada (Americans with Disabilities Act compliant, accessible to people with"
                " disabilities), Dogs (dogs allowed), DogsLeash (dogs allowed but must be leashed), DogsNo (dogs not"
                " allowed), Strollers (suitable for strollers), Paved (paved trail), PartiallyPaved (partially paved"
                " trail)."
            ),
            title="Suitability",
        ),
    ] = None
    route_type: Annotated[
        Optional[list[RouteTypeEnum]],
        Field(
            description=(
                "The type of the route. Union filter. There should be no duplicates in the route type array. Route"
                " types: O (Out and back route - goes to a point and returns to start), L (Loop route - starts and ends"
                " at the same point), P (Point to point route - starts at one point and ends at another)."
            ),
            title="Route Type",
        ),
    ] = None
    trail_traffic: Annotated[
        Optional[list[TrailTrafficEnum]],
        Field(
            description=(
                "The amount of traffic on the trail. Union filter. This is an average, an approximation, drawn from"
                " internal activity tracking data. It is not a guarantee of how many people will be on the trail at any"
                " given time. Traffic levels: light (light traffic), moderate (moderate traffic), heavy (heavy"
                " traffic)."
            ),
            title="Trail Traffic",
        ),
    ] = None


class SouthwestBounds(BaseModel):
    latitude: Annotated[float, Field(description="Latitude in decimal degrees", title="Latitude")]
    longitude: Annotated[float, Field(description="Longitude in decimal degrees", title="Longitude")]


class NortheastBounds(BaseModel):
    latitude: Annotated[float, Field(description="Latitude in decimal degrees", title="Latitude")]
    longitude: Annotated[float, Field(description="Longitude in decimal degrees", title="Longitude")]


class Input1(BaseModel):
    filters: Annotated[Optional[Filters1], Field(description="Search filters to apply")] = None
    limit: Annotated[Optional[int], Field(description="Maximum number of results", ge=1, le=20, title="Limit")] = 20
    sort: Annotated[
        Optional[Sort],
        Field(
            description=(
                "\nAbility to specify a sorting option.\n\nThe default is NONE. CRITICAL: Only extract sort if the"
                ' query contains EXPLICIT sort keywords:\n- "best trails", "top trails" → most_popular\n- "closest'
                ' trails", "nearest trails" → closest\n- "new trails", "recently added" → newly_added\n\n\nOnly include'
                " a sort option if the user's query explicitly indicates a particular sort order.\nIf no sort"
                " preference is indicated, omit the `sort` property entirely.\n\nAvailable sort options:\n- `closest`:"
                ' Sort by distance from the user\'s location. Use when the query asks for\n"closest trails" or "trails'
                ' nearest to" a location.\n- `most_popular`: Sort by overall popularity.\n- `newly_added`: Sort by date'
                ' added. Use for queries like "new hiking trails".\n- `seasonal`: Sort by popularity at the current'
                ' time of year. Use when the query asks for trails\n"at this time of year", "this season", "right now",'
                " or similar seasonal phrasing.\n- `month_1` through `month_12`: Sort by popularity in a specific"
                ' month.\nUse when the query mentions a specific month, e.g., "hiking trails in July" → `month_7`.\n'
            ),
            title="Sort",
        ),
    ] = None
    locale: Annotated[
        Optional[Locale],
        Field(
            description=(
                "A BCP 47 locale string (e.g. 'en-US', 'es-ES', 'de-DE'). Should be set to the user's device/browser"
                " locale or the language of the current conversation. Used for localizing trail names and descriptions,"
                " difficulty labels, and URLs. Falls back to request metadata if not provided."
            ),
            title="Locale",
        ),
    ] = None
    southwest_bounds: Annotated[SouthwestBounds, Field(title="Point")]
    northeast_bounds: Annotated[NortheastBounds, Field(title="Point")]


class FindTrailsWithinBoundsInput(BaseModel):
    input: Annotated[Input1, Field(title="TrailBoundsSearchInput")]


class Input2(BaseModel):
    search_query: Annotated[str, Field(description="The trail name or search query to look for", title="Search Query")]
    latitude: Annotated[
        Optional[float],
        Field(
            description="Optional latitude in decimal degrees for search that specifies a location", title="Latitude"
        ),
    ] = None
    longitude: Annotated[
        Optional[float],
        Field(
            description="Optional longitude in decimal degrees for search that specifies a location", title="Longitude"
        ),
    ] = None
    limit: Annotated[
        Optional[int],
        Field(description="Maximum number of matching trail candidates to return", ge=1, le=10, title="Limit"),
    ] = 5
    locale: Annotated[
        Optional[Locale],
        Field(
            description=(
                "A BCP 47 locale string (e.g. 'en-US', 'es-ES', 'de-DE'). Should be set to the user's device/browser"
                " locale or the language of the current conversation. Used for localizing trail names and descriptions,"
                " difficulty labels, and URLs. Falls back to request metadata if not provided."
            ),
            title="Locale",
        ),
    ] = None


class SearchTrailsByNameInput(BaseModel):
    input: Annotated[Input2, Field(title="TrailNameSearchInput")]


class Input3(BaseModel):
    trail_id: Annotated[int, Field(title="Trail Id")]
    locale: Annotated[
        Optional[Locale],
        Field(
            description=(
                "A BCP 47 locale string (e.g. 'en-US', 'es-ES', 'de-DE'). Should be set to the user's device/browser"
                " locale or the language of the current conversation. Used for localizing trail names and descriptions,"
                " difficulty labels, and URLs. Falls back to request metadata if not provided."
            ),
            title="Locale",
        ),
    ] = None


class GetTrailDetailsInput(BaseModel):
    input: Annotated[Input3, Field(title="TrailIdInput")]


class Units(Enum):
    """
    Units for temperature: 'i' for imperial (Fahrenheit), 'm' for metric (Celsius)

    Provide the unit most appropriate for the user's current locale.

    """

    I = "i"  # noqa E741
    M = "m"


class Input4(BaseModel):
    trail_id: Annotated[int, Field(description="The ID of the trail to get weather for", title="Trail Id")]
    units: Annotated[
        Optional[Units],
        Field(
            description=(
                "Units for temperature: 'i' for imperial (Fahrenheit), 'm' for metric (Celsius)\n\nProvide the unit"
                " most appropriate for the user's current locale.\n"
            ),
            title="Units",
        ),
    ] = Units.I
    locale: Annotated[
        Optional[Locale],
        Field(
            description=(
                "A BCP 47 locale string (e.g. 'en-US', 'es-ES', 'de-DE'). Should be set to the user's device/browser"
                " locale or the language of the current conversation. Used for localizing trail names and descriptions,"
                " difficulty labels, and URLs. Falls back to request metadata if not provided."
            ),
            title="Locale",
        ),
    ] = None


class GetTrailWeatherOverviewInput(BaseModel):
    input: Annotated[Input4, Field(title="WeatherInput")]
