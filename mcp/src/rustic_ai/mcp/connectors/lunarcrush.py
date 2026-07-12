"""
Auto-generated Pydantic models for lunarcrush's MCP. Supported tools are:

Example BoundMCPAgentConfig (JSON) for this provider:
 {
   "server": {
     "type": "http",
     "url": "https://lunarcrush.ai/mcp"
   },
   "tools": [
     {
       "name": "list",
       "input_class_name": "rustic_ai.mcp.connectors.lunarcrush.ListInput",
       "description": "List of social topics within a category sorted and filtered by available metrics and sectors."
     },
     {
       "name": "topic",
       "input_class_name": "rustic_ai.mcp.connectors.lunarcrush.TopicInput",
       "description": "Summary snapshot of all social metrics and insights for any social topic, keyword, cryptocurrency, stock, or custom search/collection slug like lc1s5M27Jq"
     },
     {
       "name": "topic_time_series",
       "input_class_name": "rustic_ai.mcp.connectors.lunarcrush.TopicTimeSeriesInput",
       "description": "Historical time-series metrics for a social topic, keyword, cryptocurrency, or stock, or custom search/collection slug like lc1s5M27Jq"
     },
     {
       "name": "topic_posts",
       "input_class_name": "rustic_ai.mcp.connectors.lunarcrush.TopicPostsInput",
       "description": "Top social posts by interactions for a given time period. Identify the most influential narrative and the posts driving social metrics."
     },
     {
       "name": "keyword_time_series",
       "input_class_name": "rustic_ai.mcp.connectors.lunarcrush.KeywordTimeSeriesInput",
       "description": "Historical time series social metrics for any keyword or phrase. Use for exact keyword/phrase analytics."
     },
     {
       "name": "keyword_posts",
       "input_class_name": "rustic_ai.mcp.connectors.lunarcrush.KeywordPostsInput",
       "description": "Top social posts by interactions for a given time period. Identify the most influential narrative and the posts driving social metrics. Use for exact keyword/phrase analytics."
     },
     {
       "name": "creator",
       "input_class_name": "rustic_ai.mcp.connectors.lunarcrush.CreatorInput",
       "description": "Creator's summary snapshot of social metrics and insights. Use for deeper research on a social media account/creator/influencer."
     },
     {
       "name": "creator_posts",
       "input_class_name": "rustic_ai.mcp.connectors.lunarcrush.CreatorPostsInput",
       "description": "Top social posts for a specific social media account by unique id or screen name and time period. Use for deeper research on a social media account/creator/influencer."
     },
     {
       "name": "creator_time_series",
       "input_class_name": "rustic_ai.mcp.connectors.lunarcrush.CreatorTimeSeriesInput",
       "description": "Historical time-series metrics for a social media account by unique id or screen name."
     },
     {
       "name": "post",
       "input_class_name": "rustic_ai.mcp.connectors.lunarcrush.PostInput",
       "description": "Social post details. Ids of posts can be inferred by the public URL link to the post."
     },
     {
       "name": "cryptocurrencies",
       "input_class_name": "rustic_ai.mcp.connectors.lunarcrush.CryptocurrenciesInput",
       "description": "List of cryptocurrencies sorted by available metrics and filtered by a sector."
     },
     {
       "name": "stocks",
       "input_class_name": "rustic_ai.mcp.connectors.lunarcrush.StocksInput",
       "description": "List of stocks sorted by available metrics and filtered by a sector."
     },
     {
       "name": "search",
       "input_class_name": "rustic_ai.mcp.connectors.lunarcrush.SearchInput",
       "description": "Search for any keyword or account. Returns matching topics, creator accounts, and the top social posts to help with exact topic lookup or ai context on a keyword."
     },
     {
       "name": "fetch",
       "input_class_name": "rustic_ai.mcp.connectors.lunarcrush.FetchInput",
       "description": "Fetch a lunarcrush.ai context using a specific path like /topic/bitcoin or /topic/bitcoin/posts or /list/cryptocurrencies/altrank or /creator/x/lunarcrush or /post/x/1234567890"
     }
   ]
 }

"""  # noqa

from datetime import date
from enum import Enum
from typing import Annotated, Optional

from pydantic import BaseModel, Field


class Category(Enum):
    """
    Leave blank for all categories
    """

    FASHION_BRANDS = "fashion-brands"
    TECHNOLOGY_BRANDS = "technology-brands"
    SOCIAL_NETWORKS = "social-networks"
    BUNDESLIGA = "bundesliga"
    NHL = "nhl"
    PRODUCTS = "products"
    TRAVEL_DESTINATIONS = "travel-destinations"
    LA_LIGA = "la-liga"
    AUTOMOTIVE_BRANDS = "automotive-brands"
    VC_FIRMS = "vc-firms"
    NCAA_FOOTBALL = "ncaa-football"
    LUXURY_BRANDS = "luxury-brands"
    GAMING = "gaming"
    NBA = "nba"
    NASCAR = "nascar"
    UFC = "ufc"
    AGENCIES = "agencies"
    MUSICIANS = "musicians"
    NFTS = "nfts"
    EXCHANGES = "exchanges"
    CURRENCIES = "currencies"
    CELEBRITIES = "celebrities"
    STOCKS = "stocks"
    NCAA_BASKETBALL = "ncaa-basketball"
    EVENTS = "events"
    COUNTRIES = "countries"
    MLS = "mls"
    MLB = "mlb"
    FORMULA_1 = "formula-1"
    NFL = "nfl"
    PREMIER_LEAGUE = "premier-league"
    FINANCE = "finance"
    CRYPTOCURRENCIES = "cryptocurrencies"
    CHAMPIONS_LEAGUE = "champions-league"
    PGA_GOLFERS = "pga-golfers"
    LIGA_MX = "liga-mx"


class Sort(Enum):
    """
    One of (key - display name): interactions - Engagements, posts_active - Mentions, contributors_active - Creators,
    sentiment - Sentiment, social_dominance - Social Dominance, topic_rank - TopicRank™
    """

    INTERACTIONS = "interactions"
    POSTS_ACTIVE = "posts_active"
    CONTRIBUTORS_ACTIVE = "contributors_active"
    SENTIMENT = "sentiment"
    SOCIAL_DOMINANCE = "social_dominance"
    TOPIC_RANK = "topic_rank"


class ListInput(BaseModel):
    category: Annotated[Optional[Category], Field(description="Leave blank for all categories")] = None
    limit: Annotated[Optional[float], Field(le=1000.0)] = 100
    sort: Annotated[
        Optional[Sort],
        Field(
            description=(
                "One of (key - display name): interactions - Engagements, posts_active - Mentions, contributors_active"
                " - Creators, sentiment - Sentiment, social_dominance - Social Dominance, topic_rank - TopicRank™"
            )
        ),
    ] = None


class TopicInput(BaseModel):
    topic: Annotated[
        str,
        Field(
            description=(
                "Normalized to lower case a-z, 0-9, #, $, _ and spaces are allowed. Examples: bitcoin, $btc, $nvda,"
                " trump, lebron james, gucci, lc1s5M27Jq"
            )
        ),
    ]


class Metric(Enum):
    ALT_RANK = "alt_rank"
    CIRCULATING_SUPPLY = "circulating_supply"
    CLOSE = "close"
    GALAXY_SCORE = "galaxy_score"
    HIGH = "high"
    LOW = "low"
    MARKET_CAP = "market_cap"
    MARKET_DOMINANCE = "market_dominance"
    OPEN = "open"
    VOLUME_24H = "volume_24h"
    CONTRIBUTORS_ACTIVE = "contributors_active"
    CONTRIBUTORS_CREATED = "contributors_created"
    INTERACTIONS = "interactions"
    POSTS_ACTIVE = "posts_active"
    POSTS_CREATED = "posts_created"
    SENTIMENT = "sentiment"
    SPAM = "spam"
    SOCIAL_DOMINANCE = "social_dominance"


class Interval(Enum):
    """
    Default is 1w hourly data. Use 1m or longer for daily data. One of: 1d, 1w, 1m, 3m, 6m, 1y, all
    """

    FIELD_1D = "1d"
    FIELD_1W = "1w"
    FIELD_1M = "1m"
    FIELD_3M = "3m"
    FIELD_6M = "6m"
    FIELD_1Y = "1y"
    ALL = "all"
    NONE_TYPE_NONE = None


class TopicTimeSeriesInput(BaseModel):
    topic: Annotated[
        str,
        Field(
            description=(
                "Normalized to lower case a-z, 0-9, #, $, _ and spaces are allowed. Examples: bitcoin, $btc, $nvda,"
                " trump, lebron james, gucci, lc1s5M27Jq"
            )
        ),
    ]
    metrics: Annotated[
        Optional[list[Metric]],
        Field(
            description=(
                "Leave blank to show all metrics or isolate to one or more of (key - display name): alt_rank -"
                " AltRank™, galaxy_score - Galaxy Score™, close - Price, interactions - Engagements, posts_active -"
                " Mentions, posts_created - Posts Created, contributors_active - Creators, contributors_created -"
                " Creators Posting, sentiment - Sentiment, social_dominance - Social Dominance, market_cap - Market"
                " Cap, market_dominance - Market Dominance, volume_24h - Trading Volume, circulating_supply -"
                " Circulating Supply"
            )
        ),
    ] = None
    interval: Annotated[
        Optional[Interval],
        Field(
            description=(
                "Default is 1w hourly data. Use 1m or longer for daily data. One of: 1d, 1w, 1m, 3m, 6m, 1y, all"
            )
        ),
    ] = None


class Network(Enum):
    """
    If no network is specified default is to show all
    """

    ALL = "all"
    X = "x"
    TWITTER = "twitter"
    TIKTOK = "tiktok"
    YOUTUBE = "youtube"
    REDDIT = "reddit"
    INSTAGRAM = "instagram"
    NEWS = "news"


class Interval1(Enum):
    """
    Default is most recent top posts or get the top x posts in the last 1d, 1w, 1m, 3m, 6m, 1y, all
    """

    FIELD_1D = "1d"
    FIELD_1W = "1w"
    FIELD_1M = "1m"
    FIELD_3M = "3m"
    FIELD_6M = "6m"
    FIELD_1Y = "1y"
    ALL = "all"


class TopicPostsInput(BaseModel):
    topic: Annotated[
        str,
        Field(
            description=(
                "Normalized to lower case a-z, 0-9, #, $, _ and spaces are allowed. Examples: bitcoin, $btc, $nvda,"
                " trump, lebron james, gucci, lc1s5M27Jq"
            )
        ),
    ]
    limit: Annotated[Optional[float], Field(le=1000.0)] = 100
    network: Annotated[Optional[Network], Field(description="If no network is specified default is to show all")] = None
    interval: Annotated[
        Optional[Interval1],
        Field(
            description=(
                "Default is most recent top posts or get the top x posts in the last 1d, 1w, 1m, 3m, 6m, 1y, all"
            )
        ),
    ] = None
    from_date: Annotated[
        Optional[date],
        Field(
            description=(
                "provide a date range instead of interval with from_date and to_date to get posts for a specific day or"
                " range"
            )
        ),
    ] = None
    to_date: Annotated[
        Optional[date],
        Field(description="optional to_date for date range, leave blank to get posts only from the from_date"),
    ] = None


class Metric1(Enum):
    CONTRIBUTORS_ACTIVE = "contributors_active"
    CONTRIBUTORS_CREATED = "contributors_created"
    INTERACTIONS = "interactions"
    POSTS_ACTIVE = "posts_active"
    POSTS_CREATED = "posts_created"
    SENTIMENT = "sentiment"
    SPAM = "spam"


class Interval2(Enum):
    """
    Default is 1w hourly data. Use 1m or longer for daily data. One of: 1d, 1w, 1m, 3m, 6m, 1y, all
    """

    FIELD_1W = "1w"
    FIELD_1M = "1m"
    FIELD_3M = "3m"
    FIELD_6M = "6m"
    FIELD_1Y = "1y"
    ALL = "all"


class KeywordTimeSeriesInput(BaseModel):
    keyword: Annotated[str, Field(description="Keyword examples: bitcoin, donald trump, my favorite food, taco bell")]
    metrics: Annotated[
        Optional[list[Metric1]],
        Field(
            description=(
                "Leave blank to show all metrics or isolate to one or more of (key - display name): alt_rank -"
                " AltRank™, galaxy_score - Galaxy Score™, close - Price, interactions - Engagements, posts_active -"
                " Mentions, posts_created - Posts Created, contributors_active - Creators, contributors_created -"
                " Creators Posting, sentiment - Sentiment, social_dominance - Social Dominance, market_cap - Market"
                " Cap, market_dominance - Market Dominance, volume_24h - Trading Volume, circulating_supply -"
                " Circulating Supply"
            )
        ),
    ] = None
    network: Annotated[Optional[Network], Field(description="If no network is specified default is to show all")] = None
    interval: Annotated[
        Optional[Interval2],
        Field(
            description=(
                "Default is 1w hourly data. Use 1m or longer for daily data. One of: 1d, 1w, 1m, 3m, 6m, 1y, all"
            )
        ),
    ] = None


class Interval3(Enum):
    """
    Default is most recent top posts or get the top x posts in the last 1d, 1w, 1m, 3m, 6m, 1y, all
    """

    FIELD_1D = "1d"
    FIELD_1W = "1w"
    FIELD_1M = "1m"
    FIELD_3M = "3m"
    FIELD_6M = "6m"
    FIELD_1Y = "1y"
    ALL = "all"


class KeywordPostsInput(BaseModel):
    keyword: Annotated[
        str,
        Field(
            description=(
                "Keyword/phrases must be lower case a-z, 0-9, #, $, _ and spaces are allowed. Examples: bitcoin, donald"
                " trump, my favorite food, taco bell"
            )
        ),
    ]
    limit: Annotated[Optional[float], Field(le=1000.0)] = 100
    network: Annotated[Optional[Network], Field(description="If no network is specified default is to show all")] = None
    interval: Annotated[
        Optional[Interval3],
        Field(
            description=(
                "Default is most recent top posts or get the top x posts in the last 1d, 1w, 1m, 3m, 6m, 1y, all"
            )
        ),
    ] = None
    from_date: Annotated[
        Optional[date],
        Field(
            description=(
                "provide a date range instead of interval with from_date and to_date to get posts for a specific day or"
                " range"
            )
        ),
    ] = None
    to_date: Annotated[
        Optional[date],
        Field(description="optional to_date for date range, leave blank to get posts only from the from_date"),
    ] = None


class Network3(Enum):
    X = "x"
    TWITTER = "twitter"
    TIKTOK = "tiktok"
    YOUTUBE = "youtube"
    REDDIT = "reddit"
    INSTAGRAM = "instagram"


class CreatorInput(BaseModel):
    network: Network3
    screenName: Annotated[str, Field(description="Can be the screen name or unique id")]


class CreatorPostsInput(BaseModel):
    network: Network3
    screenName: Annotated[str, Field(description="Can be the screen name or unique id")]
    limit: Annotated[Optional[float], Field(le=1000.0)] = 100
    interval: Annotated[
        Optional[Interval3],
        Field(
            description=(
                "Default is most recent top posts or get the top x posts in the last 1d, 1w, 1m, 3m, 6m, 1y, all"
            )
        ),
    ] = None
    from_date: Annotated[
        Optional[date],
        Field(
            description=(
                "provide a date range instead of interval with from_date and to_date to get posts for a specific day or"
                " range"
            )
        ),
    ] = None
    to_date: Annotated[
        Optional[date],
        Field(description="optional to_date for date range, leave blank to get posts only from the from_date"),
    ] = None


class Metric2(Enum):
    INTERACTIONS = "interactions"
    POSTS_ACTIVE = "posts_active"
    POSTS_CREATED = "posts_created"
    FOLLOWERS = "followers"
    INFLUENCER_RANK = "influencer_rank"


class Interval5(Enum):
    """
    Default is 1w hourly data. Use 1m or longer for daily data. One of: 1d, 1w, 1m, 3m, 6m, 1y, all
    """

    FIELD_1D = "1d"
    FIELD_1W = "1w"
    FIELD_1M = "1m"
    FIELD_3M = "3m"
    FIELD_6M = "6m"
    FIELD_1Y = "1y"
    ALL = "all"


class CreatorTimeSeriesInput(BaseModel):
    network: Network3
    screenName: Annotated[str, Field(description="Can be the screen name or unique id")]
    metrics: Annotated[
        Optional[list[Metric2]],
        Field(
            description=(
                "Leave blank to show all metrics or isolate to one or more of (key - display name): interactions -"
                " Engagements, posts_active - Mentions, posts_created - Posts Created, influencer_rank - CreatorRank™,"
                " followers - Followers"
            )
        ),
    ] = None
    interval: Annotated[
        Optional[Interval5],
        Field(
            description=(
                "Default is 1w hourly data. Use 1m or longer for daily data. One of: 1d, 1w, 1m, 3m, 6m, 1y, all"
            )
        ),
    ] = None


class Network6(Enum):
    X = "x"
    TWITTER = "twitter"
    TIKTOK = "tiktok"
    YOUTUBE = "youtube"
    REDDIT = "reddit"
    INSTAGRAM = "instagram"
    NEWS = "news"


class PostInput(BaseModel):
    network: Network6
    id: str


class Sector(Enum):
    """
    One of (key - display name): stablecoin - Stablecoin, defi - DeFi, nft - NFTs & Collectibles, dot - Polkadot
    Ecosystem, bsc - BNB Chain Ecosystem, meme - Memecoins, avalanche - Avalanche Ecosystem, algorand - Algorand
    Ecosystem, dao - DAO, wallets - Wallets, ai - AI, arbitrum - Arbitrum Ecosystem, gaming - Gaming & Metaverse,
    layer-1 - Layer 1, layer-2 - Layer 2, lending-borrowing - Lending/Borrowing, liquid-staking-tokens - Liquid
    Staking Derivatives, brc20 - BRC-20, exchange-tokens - Exchange Tokens, real-world-assets - Real-World Assets,
    depin - DePin, fan - Fan Tokens, gambling - Gambling, runes - Runes, desci - DeSci, sports - Sports, socialfi -
    SocialFi, analytics - Analytics, events - Events, real-estate - Real Estate, bitcoin-ecosystem - Bitcoin
    Ecosystem, stacks-ecosystem - Stacks Ecosystem, base-ecosystem - Base Ecosystem, solana-ecosystem - Solana
    Ecosystem, ai-agents - AI Agents, defai - DeFAI, zk - Zero Knowledge Proofs, oracle - Oracles, storage - Storage,
    made-in-usa - Made In USA, sui - SUI Ecosystem, inj - Injective Ecosystem, cardano - Cardano Ecosystem,
    pow - Proof of Work (PoW), pos - Proof of Stake (PoS), music - Music, insurance - Insurance, privacy - Privacy,
    energy - Energy, pump-fun - Pump.Fun Ecosystem, prediction - Prediction Markets, entertainment - Entertainment,
    healthcare - Healthcare, btcfi - BTCfi, interoperability - Interoperability, move-to-earn - Move to Earn,
    bittensor-ecosystem - Bittensor Ecosystem, derivatives - Derivatives, perpetuals - Perpetuals, openclaw -
    Moltbook and Openclaw-Themed Coins
    """

    STABLECOIN = "stablecoin"
    DEFI = "defi"
    NFT = "nft"
    DOT = "dot"
    BSC = "bsc"
    MEME = "meme"
    AVALANCHE = "avalanche"
    ALGORAND = "algorand"
    DAO = "dao"
    WALLETS = "wallets"
    AI = "ai"
    ARBITRUM = "arbitrum"
    GAMING = "gaming"
    LAYER_1 = "layer-1"
    LAYER_2 = "layer-2"
    LENDING_BORROWING = "lending-borrowing"
    LIQUID_STAKING_TOKENS = "liquid-staking-tokens"
    BRC20 = "brc20"
    EXCHANGE_TOKENS = "exchange-tokens"
    REAL_WORLD_ASSETS = "real-world-assets"
    DEPIN = "depin"
    FAN = "fan"
    GAMBLING = "gambling"
    RUNES = "runes"
    DESCI = "desci"
    SPORTS = "sports"
    SOCIALFI = "socialfi"
    ANALYTICS = "analytics"
    EVENTS = "events"
    REAL_ESTATE = "real-estate"
    BITCOIN_ECOSYSTEM = "bitcoin-ecosystem"
    STACKS_ECOSYSTEM = "stacks-ecosystem"
    BASE_ECOSYSTEM = "base-ecosystem"
    SOLANA_ECOSYSTEM = "solana-ecosystem"
    AI_AGENTS = "ai-agents"
    DEFAI = "defai"
    ZK = "zk"
    ORACLE = "oracle"
    STORAGE = "storage"
    MADE_IN_USA = "made-in-usa"
    SUI = "sui"
    INJ = "inj"
    CARDANO = "cardano"
    POW = "pow"
    POS = "pos"
    MUSIC = "music"
    INSURANCE = "insurance"
    PRIVACY = "privacy"
    ENERGY = "energy"
    PUMP_FUN = "pump-fun"
    PREDICTION = "prediction"
    ENTERTAINMENT = "entertainment"
    HEALTHCARE = "healthcare"
    BTCFI = "btcfi"
    INTEROPERABILITY = "interoperability"
    MOVE_TO_EARN = "move-to-earn"
    BITTENSOR_ECOSYSTEM = "bittensor-ecosystem"
    DERIVATIVES = "derivatives"
    PERPETUALS = "perpetuals"
    OPENCLAW = "openclaw"


class Sort1(Enum):
    """
    One of (key - display name): alt_rank - AltRank™, galaxy_score - Galaxy Score™, close - Price, percent_change_1h
    - 1h %, percent_change_24h - 24h %, percent_change_7d - 7d %, interactions - Engagements, posts_active -
    Mentions, contributors_active - Creators, sentiment - Sentiment, social_dominance - Social Dominance, market_cap
    - Market Cap, market_dominance - Market Dominance, volume_24h - Trading Volume, circulating_supply - Circulating
    Supply, topic_rank - TopicRank™
    """

    ALT_RANK = "alt_rank"
    GALAXY_SCORE = "galaxy_score"
    CLOSE = "close"
    PERCENT_CHANGE_1H = "percent_change_1h"
    PERCENT_CHANGE_24H = "percent_change_24h"
    PERCENT_CHANGE_7D = "percent_change_7d"
    INTERACTIONS = "interactions"
    POSTS_ACTIVE = "posts_active"
    CONTRIBUTORS_ACTIVE = "contributors_active"
    SENTIMENT = "sentiment"
    SOCIAL_DOMINANCE = "social_dominance"
    MARKET_CAP = "market_cap"
    MARKET_DOMINANCE = "market_dominance"
    VOLUME_24H = "volume_24h"
    CIRCULATING_SUPPLY = "circulating_supply"
    TOPIC_RANK = "topic_rank"


class CryptocurrenciesInput(BaseModel):
    sector: Annotated[
        Optional[Sector],
        Field(
            description=(
                "One of (key - display name): stablecoin - Stablecoin, defi - DeFi, nft - NFTs & Collectibles, dot -"
                " Polkadot Ecosystem, bsc - BNB Chain Ecosystem, meme - Memecoins, avalanche - Avalanche Ecosystem,"
                " algorand - Algorand Ecosystem, dao - DAO, wallets - Wallets, ai - AI, arbitrum - Arbitrum Ecosystem,"
                " gaming - Gaming & Metaverse, layer-1 - Layer 1, layer-2 - Layer 2, lending-borrowing -"
                " Lending/Borrowing, liquid-staking-tokens - Liquid Staking Derivatives, brc20 - BRC-20,"
                " exchange-tokens - Exchange Tokens, real-world-assets - Real-World Assets, depin - DePin, fan - Fan"
                " Tokens, gambling - Gambling, runes - Runes, desci - DeSci, sports - Sports, socialfi - SocialFi,"
                " analytics - Analytics, events - Events, real-estate - Real Estate, bitcoin-ecosystem - Bitcoin"
                " Ecosystem, stacks-ecosystem - Stacks Ecosystem, base-ecosystem - Base Ecosystem, solana-ecosystem -"
                " Solana Ecosystem, ai-agents - AI Agents, defai - DeFAI, zk - Zero Knowledge Proofs, oracle - Oracles,"
                " storage - Storage, made-in-usa - Made In USA, sui - SUI Ecosystem, inj - Injective Ecosystem, cardano"
                " - Cardano Ecosystem, pow - Proof of Work (PoW), pos - Proof of Stake (PoS), music - Music, insurance"
                " - Insurance, privacy - Privacy, energy - Energy, pump-fun - Pump.Fun Ecosystem, prediction -"
                " Prediction Markets, entertainment - Entertainment, healthcare - Healthcare, btcfi - BTCfi,"
                " interoperability - Interoperability, move-to-earn - Move to Earn, bittensor-ecosystem - Bittensor"
                " Ecosystem, derivatives - Derivatives, perpetuals - Perpetuals, openclaw - Moltbook and"
                " Openclaw-Themed Coins"
            )
        ),
    ] = None
    sort: Annotated[
        Optional[Sort1],
        Field(
            description=(
                "One of (key - display name): alt_rank - AltRank™, galaxy_score - Galaxy Score™, close - Price,"
                " percent_change_1h - 1h %, percent_change_24h - 24h %, percent_change_7d - 7d %, interactions -"
                " Engagements, posts_active - Mentions, contributors_active - Creators, sentiment - Sentiment,"
                " social_dominance - Social Dominance, market_cap - Market Cap, market_dominance - Market Dominance,"
                " volume_24h - Trading Volume, circulating_supply - Circulating Supply, topic_rank - TopicRank™"
            )
        ),
    ] = None
    limit: Annotated[Optional[float], Field(le=1000.0)] = 100


class Sector1(Enum):
    """
    One of (key - display name): basic-materials - Basic Materials, communication-services - Communication Services,
    consumer-cyclical - Consumer Cyclical, consumer-defensive - Consumer Defensive, energy - Energy,
    financial-services - Financial Services, healthcare - Healthcare, industrials - Industrials, real-estate - Real
    Estate, technology - Technology, utilities - Utilities, banks - Banks, etf - ETFs, bitcoin-spot-etf - Bitcoin
    Spot ETFs, bitcoin-futures-etf - Bitcoin Futures ETFs, ethereum-spot-etf - Ethereum Spot ETFs, bitcoin-treasuries
    - Bitcoin Treasuries, crypto-etfs - Crypto ETFs, defense - Defense, crypto-treasuries - Crypto Treasuries,
    bitcoin-miners - Bitcoin Miners
    """

    BASIC_MATERIALS = "basic-materials"
    COMMUNICATION_SERVICES = "communication-services"
    CONSUMER_CYCLICAL = "consumer-cyclical"
    CONSUMER_DEFENSIVE = "consumer-defensive"
    ENERGY = "energy"
    FINANCIAL_SERVICES = "financial-services"
    HEALTHCARE = "healthcare"
    INDUSTRIALS = "industrials"
    REAL_ESTATE = "real-estate"
    TECHNOLOGY = "technology"
    UTILITIES = "utilities"
    BANKS = "banks"
    ETF = "etf"
    BITCOIN_SPOT_ETF = "bitcoin-spot-etf"
    BITCOIN_FUTURES_ETF = "bitcoin-futures-etf"
    ETHEREUM_SPOT_ETF = "ethereum-spot-etf"
    BITCOIN_TREASURIES = "bitcoin-treasuries"
    CRYPTO_ETFS = "crypto-etfs"
    DEFENSE = "defense"
    CRYPTO_TREASURIES = "crypto-treasuries"
    BITCOIN_MINERS = "bitcoin-miners"


class Sort2(Enum):
    """
    One of (key - display name): alt_rank - AltRank™, galaxy_score - Galaxy Score™, close - Price, percent_change_24h
    - 24h %, interactions - Engagements, posts_active - Mentions, contributors_active - Creators, sentiment -
    Sentiment, social_dominance - Social Dominance, market_cap - Market Cap, market_dominance - Market Dominance,
    volume - Trading Volume, topic_rank - TopicRank™
    """

    ALT_RANK = "alt_rank"
    GALAXY_SCORE = "galaxy_score"
    CLOSE = "close"
    PERCENT_CHANGE_24H = "percent_change_24h"
    INTERACTIONS = "interactions"
    POSTS_ACTIVE = "posts_active"
    CONTRIBUTORS_ACTIVE = "contributors_active"
    SENTIMENT = "sentiment"
    SOCIAL_DOMINANCE = "social_dominance"
    MARKET_CAP = "market_cap"
    MARKET_DOMINANCE = "market_dominance"
    VOLUME = "volume"
    TOPIC_RANK = "topic_rank"


class StocksInput(BaseModel):
    sector: Annotated[
        Optional[Sector1],
        Field(
            description=(
                "One of (key - display name): basic-materials - Basic Materials, communication-services - Communication"
                " Services, consumer-cyclical - Consumer Cyclical, consumer-defensive - Consumer Defensive, energy -"
                " Energy, financial-services - Financial Services, healthcare - Healthcare, industrials - Industrials,"
                " real-estate - Real Estate, technology - Technology, utilities - Utilities, banks - Banks, etf - ETFs,"
                " bitcoin-spot-etf - Bitcoin Spot ETFs, bitcoin-futures-etf - Bitcoin Futures ETFs, ethereum-spot-etf -"
                " Ethereum Spot ETFs, bitcoin-treasuries - Bitcoin Treasuries, crypto-etfs - Crypto ETFs, defense -"
                " Defense, crypto-treasuries - Crypto Treasuries, bitcoin-miners - Bitcoin Miners"
            )
        ),
    ] = None
    sort: Annotated[
        Optional[Sort2],
        Field(
            description=(
                "One of (key - display name): alt_rank - AltRank™, galaxy_score - Galaxy Score™, close - Price,"
                " percent_change_24h - 24h %, interactions - Engagements, posts_active - Mentions, contributors_active"
                " - Creators, sentiment - Sentiment, social_dominance - Social Dominance, market_cap - Market Cap,"
                " market_dominance - Market Dominance, volume - Trading Volume, topic_rank - TopicRank™"
            )
        ),
    ] = None
    limit: Annotated[Optional[float], Field(le=1000.0)] = 100


class SearchInput(BaseModel):
    query: Annotated[
        str,
        Field(
            description=(
                "Search query or phrase. Include keywords, metrics, or time intervals to expand the results with more"
                " context."
            )
        ),
    ]


class FetchInput(BaseModel):
    id: Annotated[
        str,
        Field(
            description=(
                "id is a url-friendly path. Use slashes (/) to separate path parts. Example: /topic/bitcoin/posts/1m or"
                " /list/cryptocurrencies/altrank/100"
            )
        ),
    ]
