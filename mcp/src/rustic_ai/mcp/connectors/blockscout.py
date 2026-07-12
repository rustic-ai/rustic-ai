"""
Auto-generated Pydantic models for blockscout's MCP. Supported tools are:

Example BoundMCPAgentConfig (JSON) for this provider:
 {
   "server": {
     "type": "http",
     "url": "https://mcp.blockscout.com/mcp"
   },
   "tools": [
     {
       "name": "__unlock_blockchain_analysis__",
       "input_class_name": "rustic_ai.mcp.connectors.blockscout.UnlockBlockchainAnalysisInput",
       "description": "Mandatory initialization step for any session against the Blockscout MCP server.\n\n    Returns server reference data plus the `blockscout-analysis` skill pointer and URI\n    resolution rule.\n\n    MANDATORY FOR AI AGENTS: Call this tool first in every session. The returned payload\n    identifies where the operating rules and analysis framework live and how to read\n    referenced skill files before executing further tool calls.\n    "
     },
     {
       "name": "get_block_info",
       "input_class_name": "rustic_ai.mcp.connectors.blockscout.GetBlockInfoInput",
       "description": "\n    Get block information like timestamp, gas used, burnt fees, transaction count etc.\n    Can optionally include the list of transaction hashes contained in the block. Transaction hashes are omitted by default; request them only when you truly need them, because on high-traffic chains the list may exhaust the context.\n    "
     },
     {
       "name": "get_block_number",
       "input_class_name": "rustic_ai.mcp.connectors.blockscout.GetBlockNumberInput",
       "description": "\n    Retrieves the block number and timestamp for a specific date/time or the latest block.\n    Use when you need a block height for a specific point in time (e.g., \"block at 2024-01-01\")\n    or the current chain tip. If `datetime` is provided, finds the block immediately\n    preceding that time. If omitted, returns the latest indexed block.\n    "
     },
     {
       "name": "get_address_by_ens_name",
       "input_class_name": "rustic_ai.mcp.connectors.blockscout.GetAddressByEnsNameInput",
       "description": "\n    Useful for when you need to convert an ENS domain name (e.g. \"blockscout.eth\")\n    to its corresponding Ethereum address.\n    "
     },
     {
       "name": "get_transactions_by_address",
       "input_class_name": "rustic_ai.mcp.connectors.blockscout.GetTransactionsByAddressInput",
       "description": "\n    Retrieves native currency transfers and smart contract interactions (calls, internal txs) for an address.\n    **EXCLUDES TOKEN TRANSFERS**: Filters out direct token balance changes (ERC-20, etc.). You'll see calls *to* token contracts, but not the `Transfer` events. For token history, use `get_token_transfers_by_address`.\n    A single tx can have multiple records from internal calls; use `internal_transaction_index` for execution order.\n    Requires an `age_from` date to scope results for performance and relevance.\n    Use cases:\n      - `get_transactions_by_address(address, age_from)` - get all txs to/from the address since a given date.\n      - `get_transactions_by_address(address, age_from, age_to)` - get all txs to/from the address between given dates.\n      - `get_transactions_by_address(address, age_from, age_to, methods)` - get all txs to/from the address between given dates, filtered by method.\n    **SUPPORTS PAGINATION**: If response includes 'pagination' field, use the provided next_call to get additional pages.\n    "
     },
     {
       "name": "get_token_transfers_by_address",
       "input_class_name": "rustic_ai.mcp.connectors.blockscout.GetTokenTransfersByAddressInput",
       "description": "\n    Get ERC-20 token transfers for an address within a specific time range.\n    Use cases:\n      - `get_token_transfers_by_address(address, age_from)` - get all transfers of any ERC-20 token to/from the address since the given date up to the current time\n      - `get_token_transfers_by_address(address, age_from, age_to)` - get all transfers of any ERC-20 token to/from the address between the given dates\n      - `get_token_transfers_by_address(address, age_from, age_to, token)` - get all transfers of the given ERC-20 token to/from the address between the given dates\n    **SUPPORTS PAGINATION**: If response includes 'pagination' field, use the provided next_call to get additional pages.\n    "
     },
     {
       "name": "lookup_token_by_symbol",
       "input_class_name": "rustic_ai.mcp.connectors.blockscout.LookupTokenBySymbolInput",
       "description": "\n    Search for token addresses by symbol or name. Returns multiple potential\n    matches based on symbol or token name similarity. Only the first\n    ``TOKEN_RESULTS_LIMIT`` matches from the Blockscout API are returned.\n    "
     },
     {
       "name": "get_contract_abi",
       "input_class_name": "rustic_ai.mcp.connectors.blockscout.GetContractAbiInput",
       "description": "\n    Get smart contract ABI (Application Binary Interface).\n    An ABI defines all functions, events, their parameters, and return types. The ABI is required to format function calls or interpret contract data.\n    "
     },
     {
       "name": "inspect_contract_code",
       "input_class_name": "rustic_ai.mcp.connectors.blockscout.InspectContractCodeInput",
       "description": "Inspects a verified contract's source code or metadata."
     },
     {
       "name": "read_contract",
       "input_class_name": "rustic_ai.mcp.connectors.blockscout.ReadContractInput",
       "description": "\n        Calls a smart contract function (view/pure, or non-view/pure simulated via eth_call) and returns the\n        decoded result.\n\n        This tool provides a direct way to query the state of a smart contract.\n\n        Example:\n        To check the USDT balance of an address on Ethereum Mainnet, you would use the following arguments:\n    {\n      \"tool_name\": \"read_contract\",\n      \"params\": {\n        \"chain_id\": \"1\",\n        \"address\": \"0xdAC17F958D2ee523a2206206994597C13D831ec7\",\n        \"abi\": {\n          \"constant\": true,\n          \"inputs\": [{\"name\": \"_owner\", \"type\": \"address\"}],\n          \"name\": \"balanceOf\",\n          \"outputs\": [{\"name\": \"balance\", \"type\": \"uint256\"}],\n          \"payable\": false,\n          \"stateMutability\": \"view\",\n          \"type\": \"function\"\n        },\n        \"function_name\": \"balanceOf\",\n        \"args\": \"[\"0xF977814e90dA44bFA03b6295A0616a897441aceC\"]\"\n      }\n    }\n    "
     },
     {
       "name": "get_address_info",
       "input_class_name": "rustic_ai.mcp.connectors.blockscout.GetAddressInfoInput",
       "description": "\n    Get comprehensive information about an address, including:\n    - Address existence check\n    - Native token (ETH) balance (provided as is, without adjusting by decimals)\n    - First transaction details (block number and timestamp) for age calculation\n    - ENS name association (if any)\n    - Contract status (whether the address is a contract, whether it is verified)\n    - Proxy contract information (if applicable): determines if a smart contract is a proxy contract (which forwards calls to implementation contracts), including proxy type and implementation addresses\n    - Token details (if the contract is a token): name, symbol, decimals, total supply, etc.\n    Essential for address analysis, contract investigation, token research, and DeFi protocol analysis.\n    "
     },
     {
       "name": "get_tokens_by_address",
       "input_class_name": "rustic_ai.mcp.connectors.blockscout.GetTokensByAddressInput",
       "description": "\n    Get comprehensive ERC20 token holdings for an address with enriched metadata and market data.\n    Returns detailed token information including contract details (name, symbol, decimals), market metrics (exchange rate, market cap, volume), holders count, and actual balance (provided as is, without adjusting by decimals).\n    Essential for portfolio analysis, wallet auditing, and DeFi position tracking.\n    **SUPPORTS PAGINATION**: If response includes 'pagination' field, use the provided next_call to get additional pages.\n    "
     },
     {
       "name": "nft_tokens_by_address",
       "input_class_name": "rustic_ai.mcp.connectors.blockscout.NftTokensByAddressInput",
       "description": "\n    Retrieve NFT tokens (ERC-721, ERC-404, ERC-1155) owned by an address, grouped by collection.\n    Provides collection details (type, address, name, symbol, total supply, holder count) and individual token instance data (ID, name, description, external URL, metadata attributes).\n    Essential for a detailed overview of an address's digital collectibles and their associated collection data.\n    **SUPPORTS PAGINATION**: If response includes 'pagination' field, use the provided next_call to get additional pages.\n    "
     },
     {
       "name": "get_transaction_info",
       "input_class_name": "rustic_ai.mcp.connectors.blockscout.GetTransactionInfoInput",
       "description": "\n    Get comprehensive transaction information.\n    Unlike standard eth_getTransactionByHash, this tool returns enriched data including decoded input parameters, detailed token transfers with token metadata, transaction fee breakdown (priority fees, burnt fees) and categorized transaction types.\n    By default, the raw transaction input is omitted if a decoded version is available to save context; request it with `include_raw_input=True` only when you truly need the raw hex data.\n    Essential for transaction analysis, debugging smart contract interactions, tracking DeFi operations.\n    "
     },
     {
       "name": "get_chains_list",
       "input_class_name": "rustic_ai.mcp.connectors.blockscout.GetChainsListInput",
       "description": "Get supported blockchain chains with their chain IDs.\n\n    Use this when another tool needs a supported `chain_id` and only the chain name,\n    ecosystem, or native currency is known. Prefer a narrow `query` to avoid returning\n    the full registry to the agent. Do not rely on partial numeric chain ID queries such\n    as `1`, because matching is substring-based and may return many chains.\n    "
     },
     {
       "name": "direct_api_call",
       "input_class_name": "rustic_ai.mcp.connectors.blockscout.DirectApiCallInput",
       "description": "Call a raw Blockscout API endpoint for advanced or chain-specific data.\n\n    Do not include query strings in ``endpoint_path``; pass all query parameters via\n    ``query_params`` to avoid double-encoding.\n\n    **SUPPORTS PAGINATION**: If response includes 'pagination' field,\n    use the provided next_call to get additional pages (GET only).\n\n    Supports POST requests with a JSON body for endpoints like JSON RPC.\n\n    Returns:\n        ToolResponse[Any]: Must return ToolResponse[Any] (not ToolResponse[BaseModel])\n        because specialized handlers can return lists or other types that don't inherit\n        from BaseModel. The dispatcher system supports flexible data structures.\n    "
     }
   ],
   "auth_header": "Blockscout-MCP-Pro-Api-Key"
 }

"""  # noqa

from enum import Enum
from typing import Annotated, Any, Optional, Union

from pydantic import BaseModel, Field


class FieldUnlockBlockchainAnalysisInput(BaseModel):
    pass


class GetBlockInfoInput(BaseModel):
    chain_id: Annotated[str, Field(description="The ID of the blockchain", title="Chain Id")]
    number_or_hash: Annotated[str, Field(description="Block number or hash", title="Number Or Hash")]
    include_transactions: Annotated[
        Optional[bool],
        Field(
            description="If true, includes a list of transaction hashes from the block.", title="Include Transactions"
        ),
    ] = False


class GetBlockNumberInput(BaseModel):
    chain_id: Annotated[str, Field(description="The ID of the blockchain", title="Chain Id")]
    datetime: Annotated[
        Optional[str],
        Field(
            description=(
                "The date and time (ISO 8601 format, e.g. 2025-05-22T23:00:00.00Z) to find the block for. If omitted,"
                " returns the latest block."
            ),
            title="Datetime",
        ),
    ] = None


class GetAddressByEnsNameInput(BaseModel):
    name: Annotated[str, Field(description="ENS domain name to resolve", title="Name")]


class GetTransactionsByAddressInput(BaseModel):
    chain_id: Annotated[str, Field(description="The ID of the blockchain", title="Chain Id")]
    address: Annotated[
        str, Field(description="Address which either sender or receiver of the transaction", title="Address")
    ]
    age_from: Annotated[str, Field(description="Start date and time (e.g 2025-05-22T23:00:00.00Z).", title="Age From")]
    age_to: Annotated[
        Optional[str], Field(description="End date and time (e.g 2025-05-22T22:30:00.00Z).", title="Age To")
    ] = None
    methods: Annotated[
        Optional[str],
        Field(description="A method signature to filter transactions by (e.g 0x304e6ade)", title="Methods"),
    ] = None
    cursor: Annotated[
        Optional[str],
        Field(
            description="The pagination cursor from a previous response to get the next page of results.",
            title="Cursor",
        ),
    ] = None


class GetTokenTransfersByAddressInput(BaseModel):
    chain_id: Annotated[str, Field(description="The ID of the blockchain", title="Chain Id")]
    address: Annotated[
        str, Field(description="Address which either transfer initiator or transfer receiver", title="Address")
    ]
    age_from: Annotated[str, Field(description="Start date and time (e.g 2025-05-22T23:00:00.00Z).", title="Age From")]
    age_to: Annotated[
        Optional[str],
        Field(
            description=(
                "End date and time (e.g 2025-05-22T22:30:00.00Z). Can be omitted to get all transfers up to the current"
                " time."
            ),
            title="Age To",
        ),
    ] = None
    token: Annotated[
        Optional[str],
        Field(
            description=(
                "An ERC-20 token contract address to filter transfers by a specific token. If omitted, returns"
                " transfers of all tokens."
            ),
            title="Token",
        ),
    ] = None
    cursor: Annotated[
        Optional[str],
        Field(
            description="The pagination cursor from a previous response to get the next page of results.",
            title="Cursor",
        ),
    ] = None


class LookupTokenBySymbolInput(BaseModel):
    chain_id: Annotated[str, Field(description="The ID of the blockchain", title="Chain Id")]
    symbol: Annotated[str, Field(description="Token symbol or name to search for", title="Symbol")]


class GetContractAbiInput(BaseModel):
    chain_id: Annotated[str, Field(description="The ID of the blockchain", title="Chain Id")]
    address: Annotated[str, Field(description="Smart contract address", title="Address")]


class InspectContractCodeInput(BaseModel):
    chain_id: Annotated[str, Field(description="The ID of the blockchain.", title="Chain Id")]
    address: Annotated[str, Field(description="The address of the smart contract.", title="Address")]
    file_name: Annotated[
        Optional[str],
        Field(
            description=(
                "The name of the source file to inspect. If omitted, returns contract metadata and the list of source"
                " files."
            ),
            title="File Name",
        ),
    ] = None


class ReadContractInput(BaseModel):
    chain_id: Annotated[str, Field(description="The ID of the blockchain", title="Chain Id")]
    address: Annotated[str, Field(description="Smart contract address", title="Address")]
    abi: Annotated[
        dict[str, Any],
        Field(
            description=(
                "The JSON ABI for the specific function being called. This should be a dictionary that defines the"
                " function's name, inputs, and outputs. The function ABI can be obtained using the `get_contract_abi`"
                " tool."
            ),
            title="Abi",
        ),
    ]
    function_name: Annotated[
        str,
        Field(
            description=(
                "The symbolic name of the function to be called. This must match the `name` field in the provided ABI."
            ),
            title="Function Name",
        ),
    ]
    args: Annotated[
        Optional[str],
        Field(
            description=(
                'A JSON string containing an array of arguments. Example: "["0xabc..."]" for a single address argument,'
                ' or "[]" for no arguments. Order and types must match ABI inputs. Addresses: use 0x-prefixed strings;'
                ' Numbers: prefer integers (not quoted); numeric strings like "1" are also accepted and coerced to'
                " integers. Bytes: keep as 0x-hex strings."
            ),
            title="Args",
        ),
    ] = "[]"
    block: Annotated[
        Optional[Union[str, int]],
        Field(
            description=(
                "The block identifier to read the contract state from. Can be a block number (e.g., 19000000) or a"
                " string tag (e.g., 'latest'). Defaults to 'latest'."
            ),
            title="Block",
        ),
    ] = "latest"


class GetAddressInfoInput(BaseModel):
    chain_id: Annotated[str, Field(description="The ID of the blockchain", title="Chain Id")]
    address: Annotated[str, Field(description="Address to get information about", title="Address")]


class GetTokensByAddressInput(BaseModel):
    chain_id: Annotated[str, Field(description="The ID of the blockchain", title="Chain Id")]
    address: Annotated[str, Field(description="Wallet address", title="Address")]
    cursor: Annotated[
        Optional[str],
        Field(
            description="The pagination cursor from a previous response to get the next page of results.",
            title="Cursor",
        ),
    ] = None


class NftTokensByAddressInput(BaseModel):
    chain_id: Annotated[str, Field(description="The ID of the blockchain", title="Chain Id")]
    address: Annotated[str, Field(description="NFT owner address", title="Address")]
    cursor: Annotated[
        Optional[str],
        Field(
            description="The pagination cursor from a previous response to get the next page of results.",
            title="Cursor",
        ),
    ] = None


class GetTransactionInfoInput(BaseModel):
    chain_id: Annotated[str, Field(description="The ID of the blockchain", title="Chain Id")]
    transaction_hash: Annotated[str, Field(description="Transaction hash", title="Transaction Hash")]
    include_raw_input: Annotated[
        Optional[bool],
        Field(description="If true, includes the raw transaction input data.", title="Include Raw Input"),
    ] = False


class GetChainsListInput(BaseModel):
    query: Annotated[
        Optional[str],
        Field(
            description=(
                "Optional case-insensitive substring filter applied to chain name, chain ID, native currency, and"
                " ecosystem. Prefer narrow text terms over partial numeric chain IDs because matching is"
                " substring-based."
            ),
            title="Query",
        ),
    ] = None


class Method(Enum):
    """
    HTTP method used for the upstream call. Use POST with json_body.
    """

    GET = "GET"
    POST = "POST"


class DirectApiCallInput(BaseModel):
    chain_id: Annotated[str, Field(description="The ID of the blockchain", title="Chain Id")]
    endpoint_path: Annotated[
        str,
        Field(
            description="The Blockscout API path to call (e.g., '/api/v2/stats'); do not include query strings.",
            title="Endpoint Path",
        ),
    ]
    query_params: Annotated[
        Optional[dict[str, Any]],
        Field(description="Optional query parameters forwarded to the Blockscout API.", title="Query Params"),
    ] = None
    cursor: Annotated[
        Optional[str],
        Field(
            description="The pagination cursor from a previous response to get the next page of results.",
            title="Cursor",
        ),
    ] = None
    method: Annotated[
        Optional[Method],
        Field(description="HTTP method used for the upstream call. Use POST with json_body.", title="Method"),
    ] = Method.GET
    json_body: Annotated[
        Optional[dict[str, Any]], Field(description="JSON request body for POST requests.", title="Json Body")
    ] = None
