"""
Auto-generated Pydantic models for airtable's MCP. Supported tools are:

Example BoundMCPAgentConfig (JSON) for this provider:
 {
   "server": {
     "type": "http",
     "url": "https://mcp.airtable.com/mcp"
   },
   "tools": [
     {
       "name": "ping",
       "input_class_name": "rustic_ai.mcp.connectors.airtable.PingInput",
       "description": "Ping the MCP server to check if it is running"
     },
     {
       "name": "list_bases",
       "input_class_name": "rustic_ai.mcp.connectors.airtable.ListBasesInput",
       "description": "Lists all bases that you have access to in your Airtable account.\nUse this to get the baseId of the base you want to use.\nFavorited and recently viewed bases are generally more relevant.\nIf the response includes an offset, pass it in a subsequent call to retrieve the next page of results."
     },
     {
       "name": "list_workspaces",
       "input_class_name": "rustic_ai.mcp.connectors.airtable.ListWorkspacesInput",
       "description": "Lists all workspaces the current user has access to, along with their permission level in each.\nNo dependencies. This is typically the first tool to call when you need a workspaceId."
     },
     {
       "name": "search_bases",
       "input_class_name": "rustic_ai.mcp.connectors.airtable.SearchBasesInput",
       "description": "Searches for bases by name.\nThis is useful when you need to find a specific base quickly by a partial name-based match.\nReturns bases sorted by their relevance score, as well as a recommended base ID and a hint on whether\nwe need to ask the user to explicitly select the base they want to use."
     },
     {
       "name": "list_tables_for_base",
       "input_class_name": "rustic_ai.mcp.connectors.airtable.ListTablesForBaseInput",
       "description": "Gets the summary of a specific base. This includes the schemas of all tables in the\nbase, including field name and type.\nIf the base is not found or returns a permission error, the user may have interface-only access. Try list_pages_for_base instead."
     },
     {
       "name": "get_table_schema",
       "input_class_name": "rustic_ai.mcp.connectors.airtable.GetTableSchemaInput",
       "description": "Gets the detailed schema information for specified tables and fields in a base.\nThis returns the field ID, type, and config for the specified fields of the specified tables.\nExample: get schema for two fields in a table:\n{\"baseId\": \"appZfrNIUEip5MazD\", \"tables\": [{\"tableId\": \"tblGlReoTNWfYnXIG\", \"fieldIds\": [\"fld8WsrpLHHevsnW8\", \"fldgD18XtsueoiguT\"]}]}"
     },
     {
       "name": "list_records_for_table",
       "input_class_name": "rustic_ai.mcp.connectors.airtable.ListRecordsForTableInput",
       "description": "Lists records queried from an Airtable table.\nDo not assume baseId and tableId. Obtain these from search_bases \u2192 list_tables_for_base.\nDo not attempt to pass filterByFormula. Look carefully at the filters parameter.\nPre-requisite: If filtering on singleSelect/multipleSelects fields, and the choice name is not provided, you must call get_table_schema first to get the choice IDs.\nAim to provide at least 6 relevant fields via the 'fieldIds' parameter.\nNote: singleSelect and multipleSelects field values are returned as objects (e.g., {\"id\": \"sel...\", \"name\": \"Option\", \"color\": \"blue\"}) or arrays of such objects. When writing these values back via create_records_for_table or update_records_for_table, use the plain string name (e.g., \"Option\") instead of the object.\nIf the base is not found or returns a permission error, the user may have interface-only access. Try list_records_for_page instead."
     },
     {
       "name": "list_record_comments",
       "input_class_name": "rustic_ai.mcp.connectors.airtable.ListRecordCommentsInput",
       "description": "Lists comments on a specific Airtable record, ordered from newest to oldest.\nDo not assume baseId, tableId, or recordId. Obtain these from search_bases \u2192 list_tables_for_base \u2192 list_records_for_table.\nComments may contain user mentions in @[userId] or @[userGroupId] format. The mentioned field maps these IDs to display names and emails.\nSupports pagination via pageSize and offset parameters."
     },
     {
       "name": "create_record_comment",
       "input_class_name": "rustic_ai.mcp.connectors.airtable.CreateRecordCommentInput",
       "description": "Creates a comment on a specific Airtable record.\nDo not assume baseId, tableId, or recordId. Obtain these from search_bases \u2192 list_tables_for_base \u2192 list_records_for_table.\nTo mention a user or group in the comment, include @[userId] or @[userGroupId] tokens in the text. Obtain user IDs from collaborator fields in list_records_for_table results.\nSupports threaded replies via the optional parentCommentId parameter."
     },
     {
       "name": "create_records_for_table",
       "input_class_name": "rustic_ai.mcp.connectors.airtable.CreateRecordsForTableInput",
       "description": "Creates new records in an Airtable table.\nTo get baseId and tableId, use the search_bases and list_tables_for_base tools first.\nFor singleSelect/multipleSelects fields, provide the option name as a plain string (e.g., \"In progress\") or array of strings, not the object format returned by list_records_for_table.\nBy default the response includes only the fields you wrote. To also include fields you did not write (e.g. the primary field or formula results), pass their IDs in fieldIds.\nYou can create up to 50 records per request. To create more than 50 records, make multiple requests.\nExample: create a record with singleLineText, number, singleSelect, and multipleSelects fields:\n{\"baseId\": \"appZfrNIUEip5MazD\", \"tableId\": \"tblGlReoTNWfYnXIG\", \"records\": [{\"fields\": {\"fldGlRtkBNWfYnPOV\": \"Launch meeting\", \"fldulcCPDVz87Bmnw\": 42, \"fld8WsrpLHHevsnW8\": \"In progress\", \"fldgD18XtsueoiguT\": [\"Urgent\", \"Q1\"]}}]}"
     },
     {
       "name": "update_records_for_table",
       "input_class_name": "rustic_ai.mcp.connectors.airtable.UpdateRecordsForTableInput",
       "description": "Updates records in an Airtable table.\nThe fields you specify will be updated, and all other fields will be left unchanged.\nTo get baseId and tableId, consider using the search_bases and list_tables_for_base tools first.\nFor singleSelect/multipleSelects fields, provide the option name as a plain string (e.g., \"In progress\") or array of strings, not the object format returned by list_records_for_table.\nBy default the response includes only the fields you wrote. To also include fields you did not write (e.g. the primary field or formula results), pass their IDs in fieldIds.\nYou can update up to 50 records per request. To update more than 50 records, make multiple requests.\nExample: update a record's fields:\n{\"baseId\": \"appZfrNIUEip5MazD\", \"tableId\": \"tblGlReoTNWfYnXIG\", \"records\": [{\"id\": \"recZOTa3BDHxlJNzf\", \"fields\": {\"fldGlRtkBNWfYnPOV\": \"Updated name\", \"fld8WsrpLHHevsnW8\": \"Done\"}}]}"
     },
     {
       "name": "delete_records_for_table",
       "input_class_name": "rustic_ai.mcp.connectors.airtable.DeleteRecordsForTableInput",
       "description": "Deletes records from an Airtable table.\nTo get record IDs, use the list_records_for_table or search_records tools first.\nYou can delete up to 50 records per request. To delete more than 50 records, make multiple requests.\nExample: delete records by ID:\n{\"baseId\": \"appZfrNIUEip5MazD\", \"tableId\": \"tblGlReoTNWfYnXIG\", \"recordIds\": [\"recZOTa3BDHxlJNzf\", \"recABCDEFGHIJKLMN\"]}"
     },
     {
       "name": "create_base",
       "input_class_name": "rustic_ai.mcp.connectors.airtable.CreateBaseInput",
       "description": "Creates a new Airtable base with the specified tables and fields.\nRequires a workspaceId. To find workspace IDs, use list_workspaces.\nWhen tables are provided, the first field in each table's fields array becomes that table's primary field\nand must be a supported primary field type.\nExample: create a base called \"Project Tracker\" with a \"Tasks\" table:\n{\"workspaceId\": \"wspZfrNIUEip5MazD\", \"name\": \"Project Tracker\", \"tables\": [{\"name\": \"Tasks\", \"fields\": [{\"name\": \"Task Name\", \"type\": \"singleLineText\"}, {\"name\": \"Status\", \"type\": \"singleSelect\", \"options\": {\"choices\": [{\"name\": \"Todo\"}, {\"name\": \"In progress\"}, {\"name\": \"Done\"}]}}, {\"name\": \"Priority\", \"type\": \"number\", \"options\": {\"precision\": 0}}]}]}"
     },
     {
       "name": "create_table",
       "input_class_name": "rustic_ai.mcp.connectors.airtable.CreateTableInput",
       "description": "Creates a new table in an Airtable base.\nTo get baseId, use the search_bases or list_bases tools first.\nThe first field in the fields array becomes the primary field of the table.\nExample: create a table called \"Projects\" with singleLineText (Title), number (Priority), singleSelect (Status), and multipleSelects (Tags) fields:\n{\"baseId\": \"appZfrNIUEip5MazD\", \"name\": \"Projects\", \"fields\": [{\"name\": \"Title\", \"type\": \"singleLineText\"}, {\"name\": \"Priority\", \"type\": \"number\", \"options\": {\"precision\": 0}}, {\"name\": \"Status\", \"type\": \"singleSelect\", \"options\": {\"choices\": [{\"name\": \"Todo\"}, {\"name\": \"In progress\"}, {\"name\": \"Done\"}]}}, {\"name\": \"Tags\", \"type\": \"multipleSelects\", \"options\": {\"choices\": [{\"name\": \"Urgent\"}, {\"name\": \"Q1\"}]}}]}"
     },
     {
       "name": "update_table",
       "input_class_name": "rustic_ai.mcp.connectors.airtable.UpdateTableInput",
       "description": "Updates an existing table's name and/or description in an Airtable base.\nTo get baseId and tableId, use the search_bases and list_tables_for_base tools first.\nAt least one of name or description must be provided.\nExample: update a table's name and description:\n{\"baseId\": \"appZfrNIUEip5MazD\", \"tableId\": \"tblGlReoTNWfYnXIG\", \"name\": \"Updated Name\", \"description\": \"New description\"}"
     },
     {
       "name": "create_field",
       "input_class_name": "rustic_ai.mcp.connectors.airtable.CreateFieldInput",
       "description": "Creates a new field in an existing Airtable table.\nTo get baseId and tableId, use the search_bases and list_tables_for_base tools first.\nExample: create a singleSelect \"Status\" field:\n{\"baseId\": \"appZfrNIUEip5MazD\", \"tableId\": \"tblGlReoTNWfYnXIG\", \"field\": {\"name\": \"Status\", \"type\": \"singleSelect\", \"options\": {\"choices\": [{\"name\": \"Todo\"}, {\"name\": \"In progress\"}, {\"name\": \"Done\"}]}}}\nExample: create a number \"Priority\" field:\n{\"baseId\": \"appZfrNIUEip5MazD\", \"tableId\": \"tblGlReoTNWfYnXIG\", \"field\": {\"name\": \"Priority\", \"type\": \"number\", \"options\": {\"precision\": 0}}}\nExample: create a formula field (reference other fields by name or ID):\n{\"baseId\": \"appZfrNIUEip5MazD\", \"tableId\": \"tblGlReoTNWfYnXIG\", \"field\": {\"name\": \"Total\", \"type\": \"formula\", \"options\": {\"formula\": \"{Quantity} * {Price}\"}}}"
     },
     {
       "name": "update_field",
       "input_class_name": "rustic_ai.mcp.connectors.airtable.UpdateFieldInput",
       "description": "Updates the name, description, and/or options of a field in an existing Airtable table.\nAt least one of name, description, or options must be specified.\nTo get baseId and tableId, use the search_bases and list_tables_for_base tools first.\nTo get the fieldId, use the list_tables_for_base tool.\nExample: update a field's name and description:\n{\"baseId\": \"appZfrNIUEip5MazD\", \"tableId\": \"tblGlReoTNWfYnXIG\", \"fieldId\": \"fldGlRtkBNWfYnPOV\", \"name\": \"Updated Name\", \"description\": \"Updated description\"}\nExample: update a formula field's expression:\n{\"baseId\": \"appZfrNIUEip5MazD\", \"tableId\": \"tblGlReoTNWfYnXIG\", \"fieldId\": \"fldGlRtkBNWfYnPOV\", \"options\": {\"formula\": \"{Quantity} * {Price}\"}}"
     },
     {
       "name": "list_records_for_page",
       "input_class_name": "rustic_ai.mcp.connectors.airtable.ListRecordsForPageInput",
       "description": "Lists records from an interface page. Pages may display data from one table (simple pages)\nor multiple related tables (hierarchy pages, e.g. projects \u2192 tasks).\n\nThe response contains recordsByTableId, a map from table ID to the records from that table.\nFor simple pages this has one entry; for hierarchy pages it has one entry per configured level.\nUse the table IDs from list_pages_for_base to identify which table is which.\n\nUse this for bases with permissionLevel \"none\" (interface-only access), or when the user asks about interface/page data.\nObtain pageId from list_pages_for_base.\nDo not assume baseId. Obtain it from search_bases or list_bases."
     },
     {
       "name": "list_pages_for_base",
       "input_class_name": "rustic_ai.mcp.connectors.airtable.ListPagesForBaseInput",
       "description": "Lists all interfaces and their pages for a base.\nReturns metadata about each interface and the pages within it, including page IDs, names,\nand page-type-specific fields describing the page's data model or content.\n\nPages have a pageType: \"list\" pages support listing records directly,\n\"dashboard\" pages contain visualization elements (charts, big numbers, etc.)\nthat aggregate data from source tables, \"overview\" pages contain static authored\ncontent (text, links) with no record data, and \"form\" pages create records in a single table\n(top-level interface forms and standalone forms are supported; inline row forms are not).\n\nFor record list pages, use sourceTableId and tablesByTableId to understand the data model.\nFor dashboard pages, use dashboardElements to understand what each element visualizes.\nEach element's config describes the aggregation (e.g., a BigNumber with summaryFunction \"sum\"\nmeans \"sum the values of the referenced field\"). To compute these values, call\nlist_records_for_page with the element's id as elementId to fetch\nthe underlying records, then aggregate them according to the config.\nOverview pages are not backed by record data and cannot be used with\nlist_records_for_page; read their content field directly.\nFor form pages, use name, description, and sourceTableName to identify the relevant\nform. Call get_form_schema for the full form structure.\nForms may appear inside interfaces (with an interfaceId) or as standalone forms\nin the standaloneForms array (with interfaceId set to null).\nNote that the server may choose to omit form pages depending on the configuration.\n\nUse this when the user asks about interfaces, pages, dashboards, or forms, or when a base has permissionLevel \"none\" (interface-only access).\nDo not assume baseId. Obtain it from search_bases or list_bases.\n{\"baseId\": \"appZfrNIUEip5MazD\"}"
     },
     {
       "name": "get_record_for_page",
       "input_class_name": "rustic_ai.mcp.connectors.airtable.GetRecordForPageInput",
       "description": "Gets a single record's details from an interface page element.\nTakes a navigation path with a root record and edges representing linked record relationships.\nWith no edges, returns the root record. With edges, returns the last edge's linkedRecordId.\nFor each edge, fieldId is the linked record field to follow, and linkedRecordId is the record it points to.\n\nExample: record A on page P has linked record field F pointing to record B.\n- Fetch A: path = {root: {pageId: P, recordId: A}, edges: []}\n- Fetch B: path = {root: {pageId: P, recordId: A}, edges: [{fieldId: F, linkedRecordId: B}]}\nEach subsequent call appends to the same path without changing root.\n\nFor dashboard pages, include elementId in the root to identify the dashboard element.\nObtain element IDs from the dashboardElements array in the list_pages_for_base response.\n\nThe response includes navigationTargets listing which fieldIds can be expanded further.\nTo navigate deeper, append a new edge.\n\nRequires baseId and path.\nUse this for bases with permissionLevel \"none\" (interface-only access), or when the user asks about interface/page data.\nObtain pageId from list_pages_for_base.\nDo not assume baseId. Obtain it from search_bases or list_bases"
     },
     {
       "name": "search_records",
       "input_class_name": "rustic_ai.mcp.connectors.airtable.SearchRecordsInput",
       "description": "Searches for records in a table using a free-text query. Uses an optimized full-text index that supports fuzzy matching (handles typos) and token-based search (matches individual words regardless of order).\nCall list_tables_for_base first to discover available tables and fields if needed.\nPrefer this over list_records_for_table when performing free-text search on large tables. Use list_records_for_table instead when filtering by exact field values or structured filters. Not all field types are searchable. Date, rating, checkbox, and button fields are not indexed. Formula, rollup, and lookup fields are only searchable if their result type is searchable. If you need to query by unsearchable field types, use list_records_for_table with filters instead."
     },
     {
       "name": "create_interface",
       "input_class_name": "rustic_ai.mcp.connectors.airtable.CreateInterfaceInput",
       "description": "Creates a new interface within a base.\nUse list_bases or search_bases to find the appropriate baseId.\nIf requested to do so, use create_page to create a new page within the interface.\nOnce confirmed by the user, use publish_interface to publish the pages in the\ninterface to their live versions."
     },
     {
       "name": "create_page",
       "input_class_name": "rustic_ai.mcp.connectors.airtable.CreatePageInput",
       "description": "Creates a new page within an existing interface.\nSupported page types: visualization, dashboard, and customElement.\nSupported visualization types for \"visualization\" pages: kanban, list, calendar, gallery, grid, and timeline.\nUse list_bases or search_bases to find the appropriate baseId.\nUse create_interface to create a new interface to house the page, or\nlist_pages_for_base to discover existing interfaces in which to create the page.\nUse describe_page_type to discover the config shape for the chosen pageType, and\ndescribe_page_element for element-specific config.\nThe publish_interface tool can be used to publish the new page to the live\nversion of the interface after asking for confirmation from the user."
     },
     {
       "name": "delete_page",
       "input_class_name": "rustic_ai.mcp.connectors.airtable.DeletePageInput",
       "description": "Deletes an existing page from an interface, given its pageId.\nThe agent MUST ask the user for explicit confirmation before calling this tool.\nPage deletion is destructive and should not be performed without the user's go-ahead.\nUse list_pages_for_base to find the appropriate pageId.\nThe publish_interface tool can be used to publish the deletion to the live\nversion of the interface after asking for confirmation from the user."
     },
     {
       "name": "describe_page_type",
       "input_class_name": "rustic_ai.mcp.connectors.airtable.DescribePageTypeInput",
       "description": "Returns the JSON schema for a page type config.\nUse describe_page_element to discover any element-specific config required\nfor the chosen page type.\nThe returned schema describes the pageConfiguration shape required by create_page."
     },
     {
       "name": "describe_page_element",
       "input_class_name": "rustic_ai.mcp.connectors.airtable.DescribePageElementInput",
       "description": "Returns the JSON schema for a page element of the specified type.\nThe returned schema describes the element config within the pageConfiguration required by\ncreate_page."
     },
     {
       "name": "publish_interface",
       "input_class_name": "rustic_ai.mcp.connectors.airtable.PublishInterfaceInput",
       "description": "Publishes an interface, promoting each page's working draft to the live version\nthat end users see.\nPages whose publishing state is \"disabled\" are skipped and remain as drafts.\nPublishing is idempotent: re-publishing an already-published interface with no\nnew changes is a no-op.\nUse search_bases or list_bases to find the appropriate baseId.\nUse list_pages_for_base to discover interfaces and their pages.\nUse create_interface and create_page to create a new interface,\nor list_pages_for_base to discover existing interfaces, to publish."
     }
   ]
 }

"""  # noqa

from enum import Enum
from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, RootModel


class PingInput(BaseModel):
    pass


class ListBasesInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    offset: Annotated[
        Optional[str],
        Field(
            description=(
                "Pagination cursor from a previous list_bases response. Pass this to retrieve the next page of results."
            )
        ),
    ] = None


class ListWorkspacesInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    offset: Annotated[
        Optional[Union[Any, str]],
        Field(
            description=(
                "Pagination offset from the previous response. Pass this to retrieve the next page of results. Omit for"
                " the first page."
            )
        ),
    ] = None


class SearchBasesInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    searchQuery: Annotated[
        str,
        Field(
            description=(
                "The query to search for bases by name.\nThe search is case-insensitive and works with partial"
                ' matches.\nExamples: "projects", "issues", "customers"'
            )
        ),
    ]


class ListTablesForBaseInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    baseId: Annotated[
        str,
        Field(
            description=(
                'The ID of the base to get the summary of.\nMust start with "app" and is 17 characters long.\nExample:'
                ' "appZfrNIUEip5MazD".\nDo not substitute user-facing names for baseId.\nTo get baseId, use the'
                " search_bases or list_bases tool."
            ),
            pattern="^app[A-Za-z0-9]{14}$",
        ),
    ]


class FieldId(RootModel[str]):
    root: Annotated[str, Field(pattern="^fld[A-Za-z0-9]{14}$")]


class Table(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    tableId: Annotated[str, Field(pattern="^tbl[A-Za-z0-9]{14}$")]
    fieldIds: Annotated[
        list[FieldId], Field(description="The IDs of the fields to get schema information for.", min_length=1)
    ]


class GetTableSchemaInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    baseId: Annotated[
        str,
        Field(
            description=(
                'The ID of the base containing the tables.\nMust start with "app" and is 17 characters long.\nExample:'
                ' "appZfrNIUEip5MazD".\nDo not substitute user-facing names for baseId.\nTo get baseId, use the'
                " search_bases or list_bases tool."
            ),
            pattern="^app[A-Za-z0-9]{14}$",
        ),
    ]
    tables: Annotated[
        list[Table],
        Field(
            description=(
                "An array of table IDs and corresponding field IDs to get schema information for.\nMust start with"
                ' "tbl" and is 17 characters long.\nExample: "tblGlReoTNWfYnXIG".\nDo not substitute user-facing names'
                ' for tableId.\nTo get tableId, use the list_tables_for_base tool.\nField IDs must start with "fld" and'
                ' is 17 characters long.\nExample: "fldGlRtkBNWfYnPOV".\nDo not substitute user-facing names for'
                " IDs.\nTo get fieldId, use the list_tables_for_base tool."
            ),
            min_length=1,
        ),
    ]


class FieldId1(RootModel[str]):
    root: Annotated[str, Field(min_length=1)]


class Direction(Enum):
    """
    The direction to sort by.
    """

    ASC = "asc"
    DESC = "desc"


class SortItem(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    fieldId: Annotated[
        str,
        Field(
            description=(
                'The field to sort by. Accepts either a field ID (e.g., "fldGlRtkBNWfYnPOV") or field name (e.g.,'
                ' "Status").'
            ),
            min_length=1,
        ),
    ]
    direction: Annotated[Optional[Direction], Field(description="The direction to sort by.")] = None


class RecordId(RootModel[str]):
    root: Annotated[str, Field(pattern="^rec[A-Za-z0-9]{14}$")]


class Operator(Enum):
    """
    The operator to use to combine the operands (filter conditions).
    Acceptable values are 'and' and 'or'.
    The default operator is 'and'.
    """

    AND = "and"
    OR = "or"


class Operator1(Enum):
    """
    The comparison operator for this filter condition, applied to the operands. Acceptable values are =, !=, <, >,
    <=, >=, hasAnyOf, hasAllOf, isWithin, isAnyOf, isNoneOf, contains, doesNotContain, filename, fileType, isEmpty,
    isNotEmpty. For singleSelect and singleCollaborator fields, use =, !=, isAnyOf, or isNoneOf. For multipleSelects
    and multipleCollaborators fields, use hasAnyOf, hasAllOf, =, or doesNotContain.
    """

    FIELD_ = "="
    FIELD__ = "!="
    field__1 = "<"
    field__2 = ">"
    field___1 = "<="
    field___2 = ">="
    HAS_ANY_OF = "hasAnyOf"
    HAS_ALL_OF = "hasAllOf"
    IS_WITHIN = "isWithin"
    IS_ANY_OF = "isAnyOf"
    IS_NONE_OF = "isNoneOf"
    CONTAINS = "contains"
    DOES_NOT_CONTAIN = "doesNotContain"
    FILENAME = "filename"
    FILE_TYPE = "fileType"
    IS_EMPTY = "isEmpty"
    IS_NOT_EMPTY = "isNotEmpty"


class Operands(RootModel[str]):
    root: Annotated[str, Field(pattern="^fld[A-Za-z0-9]{14}$")]


class Operands1(Enum):
    IMAGE = "image"
    TEXT = "text"


class Mode(Enum):
    TODAY = "today"
    TOMORROW = "tomorrow"
    YESTERDAY = "yesterday"
    ONE_WEEK_AGO = "oneWeekAgo"
    ONE_WEEK_FROM_NOW = "oneWeekFromNow"
    ONE_MONTH_AGO = "oneMonthAgo"
    ONE_MONTH_FROM_NOW = "oneMonthFromNow"


class Operands2(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    mode: Mode
    timeZone: Annotated[str, Field(description='IANA time zone identifier (e.g., "America/New_York").')]


class Mode1(Enum):
    EXACT_DATE = "exactDate"


class Operands3(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    mode: Mode1
    exactDate: str
    timeZone: Annotated[str, Field(description='IANA time zone identifier (e.g., "America/New_York").')]


class Mode2(Enum):
    DAYS_AGO = "daysAgo"
    DAYS_FROM_NOW = "daysFromNow"


class Operands4(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    mode: Mode2
    numberOfDays: Annotated[int, Field(ge=0)]
    timeZone: Annotated[str, Field(description='IANA time zone identifier (e.g., "America/New_York").')]


class Mode3(Enum):
    PAST_WEEK = "pastWeek"
    PAST_MONTH = "pastMonth"
    PAST_YEAR = "pastYear"
    NEXT_WEEK = "nextWeek"
    NEXT_MONTH = "nextMonth"
    NEXT_YEAR = "nextYear"
    THIS_WEEK_TO_DATE = "thisWeekToDate"
    THIS_MONTH_TO_DATE = "thisMonthToDate"
    THIS_YEAR_TO_DATE = "thisYearToDate"
    THIS_CALENDAR_WEEK = "thisCalendarWeek"
    THIS_CALENDAR_MONTH = "thisCalendarMonth"
    THIS_CALENDAR_YEAR = "thisCalendarYear"


class Operands5(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    mode: Mode3
    timeZone: Annotated[str, Field(description='IANA time zone identifier (e.g., "America/New_York").')]


class Mode4(Enum):
    NEXT_NUMBER_OF_DAYS = "nextNumberOfDays"
    PAST_NUMBER_OF_DAYS = "pastNumberOfDays"


class Operands6(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    mode: Mode4
    numberOfDays: Annotated[int, Field(ge=0)]
    timeZone: Annotated[str, Field(description='IANA time zone identifier (e.g., "America/New_York").')]


class OperatorOptions(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    matchGroupsByMembership: Annotated[
        Optional[bool],
        Field(
            description=(
                "Only set this when operand is a collaborator field.\nWhen true, groups are matched by their individual"
                " members.\nWhen false, groups are matched by their literal group ID."
            )
        ),
    ] = None


class Operand(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    operator: Annotated[
        Operator1,
        Field(
            description=(
                "The comparison operator for this filter condition, applied to the operands.\nAcceptable values are =,"
                " !=, <, >, <=, >=, hasAnyOf, hasAllOf, isWithin, isAnyOf, isNoneOf, contains, doesNotContain,"
                " filename, fileType, isEmpty, isNotEmpty.\nFor singleSelect and singleCollaborator fields, use =, !=,"
                " isAnyOf, or isNoneOf.\nFor multipleSelects and multipleCollaborators fields, use hasAnyOf, hasAllOf,"
                " =, or doesNotContain."
            )
        ),
    ]
    operands: Annotated[
        list[
            Union[
                Operands,
                Optional[
                    Union[
                        str,
                        float,
                        bool,
                        list[str],
                        Operands1,
                        Union[Operands2, Operands3, Operands4],
                        Union[Operands5, Operands6],
                    ]
                ],
            ]
        ],
        Field(
            description=(
                "The operands (arguments) to the comparison operator.\nThe first operand must be a field ID. Example:"
                ' "fld9x4rqyBSCLzsJM". Do not substitute user-facing names for IDs.\nThe second operand depends on the'
                " operator and field type:\n    - isEmpty, isNotEmpty: No second operand (use a single-element array"
                " with just the field ID).\n    - =, !=, contains, doesNotContain: A string for text fields, a number"
                " for number fields, a boolean for checkbox fields.\n    - <, >, <=, >=: A number.\n    - For"
                " singleSelect/multipleSelects fields: The second operand must be a choice ID (e.g.,"
                ' "selABCDEFGHIJKLM") obtained from get_table_schema, not the choice\n    name.\n    - hasAnyOf,'
                " hasAllOf, isAnyOf, isNoneOf, doesNotContain: An array of strings (e.g., choice IDs for select fields,"
                " collaborator IDs for collaborator fields).\n    - For date/datetime fields with =, !=, <, >, <=, >=:"
                ' The second operand is a date value object, e.g. {"mode": "today", "timeZone": "America/New_York"},'
                ' {"mode": "exactDate",\n    "exactDate": "2024-01-15", "timeZone": "America/New_York"}, or {"mode":'
                ' "daysAgo", "numberOfDays": 7, "timeZone": "America/New_York"}.\n    - isWithin (date fields only):'
                ' The second operand is a date range object, e.g. {"mode": "pastWeek", "timeZone": "America/New_York"},'
                ' {"mode": "pastNumberOfDays", "numberOfDays":\n    30, "timeZone": "America/New_York"}.\n    -'
                ' filename: A string to match against attachment filenames.\n    - fileType: Either "image" or'
                ' "text".\nFor singleSelect/multipleSelects fields, the second operand must be a choice ID (e.g.,'
                ' "selet1KAKDTOhXQJk") obtained from get_table_schema.'
            ),
            max_length=2,
            min_length=1,
        ),
    ]
    operatorOptions: Optional[OperatorOptions] = None


class Filters(BaseModel):
    """
    Describes the filters to apply to the records using a structured format. Example filter where the value of the
    field with ID "fld8WsrpLHHevsnW8" is "orange" or the value of the field with ID "fldulcCPDVz87Bmnw" is greater
    than 5: {"operator": "or", "operands": [{"operator": "=", "operands": ["fld8WsrpLHHevsnW8", "orange"]},
    {"operator": ">", "operands": ["fldulcCPDVz87Bmnw", 5]}]} Example filter where the value of the collaborator
    field with ID "fldCRi9oz2vRLcIWr" can be any user in a group with ID "ugpDUVUnftA7H9bG8" and the value of the
    field with ID "fldgD18XtsueoiguT" equals select option with ID "selha8nGNAT5ATR7P": {"operator": "and",
    "operands": [{"operator": "hasAnyOf", "operands": ["fldCRi9oz2vRLcIWr", "ugpDUVUnftA7H9bG8"], "operatorOptions":
    {"matchGroupsByMembership": true}}, {"operator": "=", "operands": ["fldgD18XtsueoiguT", "selha8nGNAT5ATR7P"]}]}
    Example filter for records where a date field is within the past week: {"operands": [{"operator": "isWithin",
    "operands": ["fldABC12345678x", {"mode": "pastWeek", "timeZone": "America/New_York"}]}]} Example filter for
    records where a field is not empty: {"operands": [{"operator": "isNotEmpty", "operands": ["fldABC12345678x"]}]}
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    operator: Annotated[
        Optional[Operator],
        Field(
            description=(
                "The operator to use to combine the operands (filter conditions).\nAcceptable values are 'and' and"
                " 'or'.\nThe default operator is 'and'."
            )
        ),
    ] = None
    operands: Annotated[
        list[Operand],
        Field(
            description=(
                "A list of filter conditions to apply to the records. These are combined using the top-level operator"
                ' (default "and").\nEach filter condition must have an "operator" key (the comparison operator, e.g.'
                ' "=", "contains", "isEmpty", etc) and an "operands" key (an array where\nthe first element is a field'
                ' ID and the optional second element is the value to compare against).\nExample: [{"operator":'
                ' "contains", "operands": ["fld9x4rqyBSCLzsJM", "apple"]}]'
            ),
            max_length=50,
            min_length=1,
        ),
    ]


class ListRecordsForTableInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    baseId: Annotated[
        str,
        Field(
            description=(
                'The ID of the base containing the table.\nMust start with "app" and is 17 characters long.\nExample:'
                ' "appZfrNIUEip5MazD".\nDo not substitute user-facing names for baseId.\nTo get baseId, use the'
                " search_bases or list_bases tool."
            ),
            pattern="^app[A-Za-z0-9]{14}$",
        ),
    ]
    tableId: Annotated[
        str,
        Field(
            description=(
                'The table to list records from.\nAccepts either a table ID (e.g., "tblGlReoTNWfYnXIG") or a table name'
                ' (e.g., "Orders").\nNames are resolved case-insensitively within the base.\nTo discover tables, use'
                " the list_tables_for_base tool."
            ),
            min_length=1,
        ),
    ]
    fieldIds: Annotated[
        Optional[list[FieldId1]],
        Field(
            description=(
                "Only data for fields whose IDs or names are in this list will be included in the result.\nPass in only"
                " the fields most useful for the user to see.\nIf not provided, all fields will be included in the"
                ' result.\nAccepts either a field ID (e.g., "fldGlRtkBNWfYnPOV") or a field name (e.g.,'
                ' "Status").\nNames are resolved case-sensitively within the table.\nTo discover fields, use the'
                " list_tables_for_base tool."
            )
        ),
    ] = None
    pageSize: Annotated[
        Optional[int],
        Field(
            description=(
                "The maximum number of records to return in the response.\nThe server may respond with fewer records"
                " than this value when the total set has fewer records than this value.\nDefaults to 1000."
            ),
            gt=0,
            le=8000,
        ),
    ] = None
    cursor: Annotated[
        Optional[str],
        Field(
            description=(
                "The cursor to start from. To begin from the first record, do not include a cursor.\nFor a subsequent"
                " paginated request, include the nextCursor from the previous response."
            ),
            min_length=1,
        ),
    ] = None
    sort: Annotated[
        Optional[list[SortItem]],
        Field(
            description=(
                "A list of sort objects that specifies how the records will be ordered.\nEach sort object must have a"
                " fieldId key specifying the field to sort on (ID or name), and an optional direction key that is"
                ' either "asc" or "desc".\nThe default direction is "asc".\nRecords are sorted by the first sort object'
                " first, then by the second sort object for records that have the same value for the first sort, and so"
                ' on.\nExample sort by a single field in descending order: [{"fieldId": "Status", "direction":'
                ' "desc"}]\nExample sort by two fields, first ascending then descending: [{"fieldId": "Priority",'
                ' "direction": "asc"}, {"fieldId": "Created", "direction": "desc"}]'
            )
        ),
    ] = None
    recordIds: Annotated[
        Optional[list[RecordId]],
        Field(
            description=(
                "An array of record IDs to filter by. Only records with these IDs will be returned.\nMust start with"
                ' "rec" and is 17 characters long.\nExample: "recZOTa3BDHxlJNzf".\nDo not substitute user-facing names'
                " for IDs\nTo get recordId, use the list_records_for_table tool or display_records_for_table tools."
            ),
            min_length=1,
        ),
    ] = None
    filters: Annotated[
        Optional[Filters],
        Field(
            description=(
                "Describes the filters to apply to the records using a structured format.\nExample filter where the"
                ' value of the field with ID "fld8WsrpLHHevsnW8" is "orange" or the value of the field with ID'
                ' "fldulcCPDVz87Bmnw" is greater than 5:\n{"operator": "or", "operands": [{"operator": "=", "operands":'
                ' ["fld8WsrpLHHevsnW8", "orange"]}, {"operator": ">", "operands": ["fldulcCPDVz87Bmnw", 5]}]}\nExample'
                ' filter where the value of the collaborator field with ID "fldCRi9oz2vRLcIWr" can be any user in a'
                ' group with ID "ugpDUVUnftA7H9bG8" and the value of the field with ID "fldgD18XtsueoiguT" equals'
                ' select option with ID "selha8nGNAT5ATR7P":\n{"operator": "and", "operands": [{"operator": "hasAnyOf",'
                ' "operands": ["fldCRi9oz2vRLcIWr", "ugpDUVUnftA7H9bG8"], "operatorOptions":'
                ' {"matchGroupsByMembership": true}}, {"operator": "=", "operands": ["fldgD18XtsueoiguT",'
                ' "selha8nGNAT5ATR7P"]}]}\nExample filter for records where a date field is within the past'
                ' week:\n{"operands": [{"operator": "isWithin", "operands": ["fldABC12345678x", {"mode": "pastWeek",'
                ' "timeZone": "America/New_York"}]}]}\nExample filter for records where a field is not'
                ' empty:\n{"operands": [{"operator": "isNotEmpty", "operands": ["fldABC12345678x"]}]}'
            )
        ),
    ] = None


class ListRecordCommentsInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    baseId: Annotated[
        str,
        Field(
            description=(
                'The ID of the base.\nMust start with "app" and is 17 characters long.\nExample:'
                ' "appZfrNIUEip5MazD".\nDo not substitute user-facing names for baseId.\nTo get baseId, use the'
                " search_bases or list_bases tool."
            ),
            pattern="^app[A-Za-z0-9]{14}$",
        ),
    ]
    tableId: Annotated[
        str,
        Field(
            description=(
                'The ID of the table.\nMust start with "tbl" and is 17 characters long.\nExample:'
                ' "tblGlReoTNWfYnXIG".\nDo not substitute user-facing names for tableId.\nTo get tableId, use the'
                " list_tables_for_base tool."
            ),
            pattern="^tbl[A-Za-z0-9]{14}$",
        ),
    ]
    recordId: Annotated[
        str,
        Field(
            description=(
                'The ID of the record.\nMust start with "rec" and is 17 characters long.\nExample:'
                ' "recZOTa3BDHxlJNzf".\nDo not substitute user-facing names for IDs\nTo get recordId, use the'
                " list_records_for_table tool or display_records_for_table tools."
            ),
            pattern="^rec[A-Za-z0-9]{14}$",
        ),
    ]
    pageSize: Annotated[
        Optional[int],
        Field(description="The number of comments to return per page. Maximum and default is 100.", gt=0, le=100),
    ] = None
    offset: Annotated[
        Optional[str], Field(description="Pass the offset from a previous response to fetch the next page.")
    ] = None


class CreateRecordCommentInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    baseId: Annotated[
        str,
        Field(
            description=(
                'The ID of the base.\nMust start with "app" and is 17 characters long.\nExample:'
                ' "appZfrNIUEip5MazD".\nDo not substitute user-facing names for baseId.\nTo get baseId, use the'
                " search_bases or list_bases tool."
            ),
            pattern="^app[A-Za-z0-9]{14}$",
        ),
    ]
    tableId: Annotated[
        str,
        Field(
            description=(
                'The ID of the table.\nMust start with "tbl" and is 17 characters long.\nExample:'
                ' "tblGlReoTNWfYnXIG".\nDo not substitute user-facing names for tableId.\nTo get tableId, use the'
                " list_tables_for_base tool."
            ),
            pattern="^tbl[A-Za-z0-9]{14}$",
        ),
    ]
    recordId: Annotated[
        str,
        Field(
            description=(
                'The ID of the record.\nMust start with "rec" and is 17 characters long.\nExample:'
                ' "recZOTa3BDHxlJNzf".\nDo not substitute user-facing names for IDs\nTo get recordId, use the'
                " list_records_for_table tool or display_records_for_table tools."
            ),
            pattern="^rec[A-Za-z0-9]{14}$",
        ),
    ]
    text: Annotated[
        str,
        Field(
            description=(
                "The text of the comment to create. To mention a user or group, include @[userId] or @[userGroupId]"
                " tokens in the text."
            ),
            max_length=10000,
            min_length=1,
        ),
    ]
    parentCommentId: Annotated[
        Optional[str],
        Field(
            description=(
                "The ID of the parent comment to reply to, for creating a threaded reply. Obtain comment IDs from"
                " list_record_comments."
            )
        ),
    ] = None


class Record(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    fields: Annotated[
        dict[str, Any],
        Field(
            description=(
                "An object containing field IDs as keys and field values as values.\nField values should match the"
                " field type (e.g., strings for singleLineText fields,\nnumbers for numeric fields, arrays of strings"
                " for multipleSelects fields).\nFor singleSelect fields, use the option name as a plain string (e.g.,"
                ' "Done").\nFor multipleSelects fields, use an array of option name strings (e.g., ["Tag1",'
                ' "Tag2"]).\nField IDs must start with "fld" and is 17 characters long.\nExample:'
                ' "fldGlRtkBNWfYnPOV".\nDo not substitute user-facing names for IDs.\nTo get fieldId, use the'
                " list_tables_for_base tool."
            )
        ),
    ]


class FieldId2(RootModel[str]):
    root: Annotated[str, Field(pattern="^fld[A-Za-z0-9]{14}$")]


class CreateRecordsForTableInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    baseId: Annotated[
        str,
        Field(
            description=(
                'The ID of the base containing the table.\nMust start with "app" and is 17 characters long.\nExample:'
                ' "appZfrNIUEip5MazD".\nDo not substitute user-facing names for baseId.\nTo get baseId, use the'
                " search_bases or list_bases tool."
            ),
            pattern="^app[A-Za-z0-9]{14}$",
        ),
    ]
    tableId: Annotated[
        str,
        Field(
            description=(
                'The ID of the table to create a record in.\nMust start with "tbl" and is 17 characters long.\nExample:'
                ' "tblGlReoTNWfYnXIG".\nDo not substitute user-facing names for tableId.\nTo get tableId, use the'
                " list_tables_for_base tool."
            ),
            pattern="^tbl[A-Za-z0-9]{14}$",
        ),
    ]
    records: Annotated[
        list[Record],
        Field(
            description=(
                'An array of record objects to create. Each record must have a "fields" property\ncontaining the field'
                " values."
            ),
            min_length=1,
        ),
    ]
    typecast: Annotated[
        Optional[bool],
        Field(
            description=(
                "Whether or not to perform best-effort automatic data conversion from string values.\nDefaults to false"
                " to preserve data integrity."
            )
        ),
    ] = None
    fieldIds: Annotated[
        Optional[list[FieldId2]],
        Field(
            description=(
                "The IDs of the fields to include in each returned record.\nIf omitted, only the fields you wrote (the"
                " keys of records[].fields, unioned across all input records) are returned.\nPass explicit IDs to"
                " include fields you did not write (e.g. the primary field or formula/rollup results).\nField IDs must"
                ' start with "fld" and is 17 characters long.\nExample: "fldGlRtkBNWfYnPOV".\nDo not substitute'
                " user-facing names for IDs.\nTo get fieldId, use the list_tables_for_base tool."
            )
        ),
    ] = None


class Record1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[
        Optional[str],
        Field(
            description=(
                'The ID of the record to update.\nRequired when performUpsert is not set.\nMust start with "rec" and is'
                ' 17 characters long.\nExample: "recZOTa3BDHxlJNzf".\nDo not substitute user-facing names for IDs\nTo'
                " get recordId, use the list_records_for_table tool or display_records_for_table tools."
            ),
            pattern="^rec[A-Za-z0-9]{14}$",
        ),
    ] = None
    fields: Annotated[
        dict[str, Any],
        Field(
            description=(
                "An object containing field IDs as keys and field values as values.\nField values should match the"
                " field type (e.g., strings for singleLineText fields,\nnumbers for numeric fields, arrays of strings"
                " for multipleSelects fields).\nFor singleSelect fields, use the option name as a plain string (e.g.,"
                ' "Done").\nFor multipleSelects fields, use an array of option name strings (e.g., ["Tag1",'
                ' "Tag2"]).\nField IDs must start with "fld" and is 17 characters long.\nExample:'
                ' "fldGlRtkBNWfYnPOV".\nDo not substitute user-facing names for IDs.\nTo get fieldId, use the'
                " list_tables_for_base tool."
            )
        ),
    ]


class PerformUpsert(BaseModel):
    """
    Enables upsert behavior when set.
    When upserting is enabled, the recordId parameter is optional.
    Records that do not include a recordId will use the fields chosen by the fieldIdsToMergeOn parameter to match with existing records.
    - If no matches are found, a new record will be created.
    - If a match is found, that record will be updated.
    - If multiple matches are found, the request will fail.
    Records that include id will ignore fieldIdsToMergeOn and behave as normal updates.
    If no record with the given id exists, the request will fail and will not create a new record
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    fieldIdsToMergeOn: Annotated[
        list[str],
        Field(
            description=(
                "An array of field IDs that will be used to match records for updates.\nThese fields must be unique and"
                ' must not be computed fields (formulas, lookups, rollups).\nField IDs must start with "fld" and is 17'
                ' characters long.\nExample: "fldGlRtkBNWfYnPOV".\nDo not substitute user-facing names for IDs.\nTo get'
                " fieldId, use the list_tables_for_base tool."
            )
        ),
    ]


class UpdateRecordsForTableInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    baseId: Annotated[
        str,
        Field(
            description=(
                'The ID of the base containing the table.\nMust start with "app" and is 17 characters long.\nExample:'
                ' "appZfrNIUEip5MazD".\nDo not substitute user-facing names for baseId.\nTo get baseId, use the'
                " search_bases or list_bases tool."
            ),
            pattern="^app[A-Za-z0-9]{14}$",
        ),
    ]
    tableId: Annotated[
        str,
        Field(
            description=(
                'The ID of the table to update records in.\nMust start with "tbl" and is 17 characters long.\nExample:'
                ' "tblGlReoTNWfYnXIG".\nDo not substitute user-facing names for tableId.\nTo get tableId, use the'
                " list_tables_for_base tool."
            ),
            pattern="^tbl[A-Za-z0-9]{14}$",
        ),
    ]
    records: Annotated[
        list[Record1],
        Field(
            description=(
                'An array of record objects to update. Each record must have a "fields" property\ncontaining the field'
                " values."
            ),
            min_length=1,
        ),
    ]
    performUpsert: Annotated[
        Optional[PerformUpsert],
        Field(
            description=(
                "Enables upsert behavior when set.\nWhen upserting is enabled, the recordId parameter is"
                " optional.\nRecords that do not include a recordId will use the fields chosen by the fieldIdsToMergeOn"
                " parameter to match with existing records.\n- If no matches are found, a new record will be"
                " created.\n- If a match is found, that record will be updated.\n- If multiple matches are found, the"
                " request will fail.\nRecords that include id will ignore fieldIdsToMergeOn and behave as normal"
                " updates.\nIf no record with the given id exists, the request will fail and will not create a new"
                " record"
            )
        ),
    ] = None
    typecast: Annotated[
        Optional[bool],
        Field(
            description=(
                "Whether or not to perform best-effort automatic data conversion from string values.\nDefaults to false"
                " to preserve data integrity."
            )
        ),
    ] = None
    fieldIds: Annotated[
        Optional[list[FieldId2]],
        Field(
            description=(
                "The IDs of the fields to include in each returned record.\nIf omitted, only the fields you wrote (the"
                " keys of records[].fields, unioned across all input records) are returned.\nPass explicit IDs to"
                " include fields you did not write (e.g. the primary field or formula/rollup results).\nField IDs must"
                ' start with "fld" and is 17 characters long.\nExample: "fldGlRtkBNWfYnPOV".\nDo not substitute'
                " user-facing names for IDs.\nTo get fieldId, use the list_tables_for_base tool."
            )
        ),
    ] = None


class DeleteRecordsForTableInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    baseId: Annotated[
        str,
        Field(
            description=(
                'The ID of the base containing the table.\nMust start with "app" and is 17 characters long.\nExample:'
                ' "appZfrNIUEip5MazD".\nDo not substitute user-facing names for baseId.\nTo get baseId, use the'
                " search_bases or list_bases tool."
            ),
            pattern="^app[A-Za-z0-9]{14}$",
        ),
    ]
    tableId: Annotated[
        str,
        Field(
            description=(
                'The ID of the table to delete records from.\nMust start with "tbl" and is 17 characters'
                ' long.\nExample: "tblGlReoTNWfYnXIG".\nDo not substitute user-facing names for tableId.\nTo get'
                " tableId, use the list_tables_for_base tool."
            ),
            pattern="^tbl[A-Za-z0-9]{14}$",
        ),
    ]
    recordIds: Annotated[
        list[RecordId],
        Field(
            description=(
                'An array of record IDs to delete.\nMust start with "rec" and is 17 characters long.\nExample:'
                ' "recZOTa3BDHxlJNzf".\nDo not substitute user-facing names for IDs\nTo get recordId, use the'
                " list_records_for_table tool or display_records_for_table tools."
            ),
            min_length=1,
        ),
    ]


class Type(Enum):
    SINGLE_COLLABORATOR = "singleCollaborator"
    MULTIPLE_COLLABORATORS = "multipleCollaborators"
    SINGLE_LINE_TEXT = "singleLineText"
    EMAIL = "email"
    URL = "url"
    MULTILINE_TEXT = "multilineText"
    PHONE_NUMBER = "phoneNumber"
    RICH_TEXT = "richText"
    BARCODE = "barcode"
    MULTIPLE_ATTACHMENTS = "multipleAttachments"


class Fields(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        str, Field(description="Field names must be unique within the table (case-insensitive).", min_length=1)
    ]
    description: Annotated[Optional[str], Field(max_length=20000)] = None
    type: Type


class Type1(Enum):
    CHECKBOX = "checkbox"


class Icon(Enum):
    """
    Checkbox icon. Use "check" for a standard checkbox.
    """

    CHECK = "check"
    X_CHECKBOX = "xCheckbox"
    STAR = "star"
    HEART = "heart"
    THUMBS_UP = "thumbsUp"
    FLAG = "flag"
    DOT = "dot"


class Color(Enum):
    """
    Checkbox color. Use "greenBright" for a standard checkbox.
    """

    GREEN_BRIGHT = "greenBright"
    TEAL_BRIGHT = "tealBright"
    CYAN_BRIGHT = "cyanBright"
    BLUE_BRIGHT = "blueBright"
    PURPLE_BRIGHT = "purpleBright"
    PINK_BRIGHT = "pinkBright"
    RED_BRIGHT = "redBright"
    ORANGE_BRIGHT = "orangeBright"
    YELLOW_BRIGHT = "yellowBright"
    GRAY_BRIGHT = "grayBright"


class Options(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    icon: Annotated[Icon, Field(description='Checkbox icon. Use "check" for a standard checkbox.')]
    color: Annotated[Color, Field(description='Checkbox color. Use "greenBright" for a standard checkbox.')]


class Fields1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        str, Field(description="Field names must be unique within the table (case-insensitive).", min_length=1)
    ]
    description: Annotated[Optional[str], Field(max_length=20000)] = None
    type: Type1
    options: Options


class Type2(Enum):
    SINGLE_SELECT = "singleSelect"
    MULTIPLE_SELECTS = "multipleSelects"


class Color1(Enum):
    """
    Colors are auto-assigned if omitted.
    """

    BLUE_LIGHT2 = "blueLight2"
    CYAN_LIGHT2 = "cyanLight2"
    TEAL_LIGHT2 = "tealLight2"
    GREEN_LIGHT2 = "greenLight2"
    YELLOW_LIGHT2 = "yellowLight2"
    ORANGE_LIGHT2 = "orangeLight2"
    RED_LIGHT2 = "redLight2"
    PINK_LIGHT2 = "pinkLight2"
    PURPLE_LIGHT2 = "purpleLight2"
    GRAY_LIGHT2 = "grayLight2"
    BLUE_LIGHT1 = "blueLight1"
    CYAN_LIGHT1 = "cyanLight1"
    TEAL_LIGHT1 = "tealLight1"
    GREEN_LIGHT1 = "greenLight1"
    YELLOW_LIGHT1 = "yellowLight1"
    ORANGE_LIGHT1 = "orangeLight1"
    RED_LIGHT1 = "redLight1"
    PINK_LIGHT1 = "pinkLight1"
    PURPLE_LIGHT1 = "purpleLight1"
    GRAY_LIGHT1 = "grayLight1"
    BLUE_BRIGHT = "blueBright"
    CYAN_BRIGHT = "cyanBright"
    TEAL_BRIGHT = "tealBright"
    GREEN_BRIGHT = "greenBright"
    YELLOW_BRIGHT = "yellowBright"
    ORANGE_BRIGHT = "orangeBright"
    RED_BRIGHT = "redBright"
    PINK_BRIGHT = "pinkBright"
    PURPLE_BRIGHT = "purpleBright"
    GRAY_BRIGHT = "grayBright"
    BLUE_DARK1 = "blueDark1"
    CYAN_DARK1 = "cyanDark1"
    TEAL_DARK1 = "tealDark1"
    GREEN_DARK1 = "greenDark1"
    YELLOW_DARK1 = "yellowDark1"
    ORANGE_DARK1 = "orangeDark1"
    RED_DARK1 = "redDark1"
    PINK_DARK1 = "pinkDark1"
    PURPLE_DARK1 = "purpleDark1"
    GRAY_DARK1 = "grayDark1"


class Choice(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: str
    color: Annotated[Optional[Color1], Field(description="Colors are auto-assigned if omitted.")] = None


class Options1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    choices: Annotated[list[Choice], Field(max_length=10000)]


class Fields2(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        str, Field(description="Field names must be unique within the table (case-insensitive).", min_length=1)
    ]
    description: Annotated[Optional[str], Field(max_length=20000)] = None
    type: Type2
    options: Options1


class Type3(Enum):
    NUMBER = "number"


class Options2(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    precision: Annotated[int, Field(description="Number of decimal places.", ge=0, le=8)]


class Fields3(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        str, Field(description="Field names must be unique within the table (case-insensitive).", min_length=1)
    ]
    description: Annotated[Optional[str], Field(max_length=20000)] = None
    type: Type3
    options: Options2


class Type4(Enum):
    PERCENT = "percent"


class Fields4(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        str, Field(description="Field names must be unique within the table (case-insensitive).", min_length=1)
    ]
    description: Annotated[Optional[str], Field(max_length=20000)] = None
    type: Type4
    options: Options2


class Type5(Enum):
    CURRENCY = "currency"


class Options4(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    precision: Annotated[int, Field(description="Number of decimal places.", ge=0, le=7)]
    symbol: Annotated[str, Field(description='Currency symbol, e.g. "$", "€", "£", "¥".', max_length=100)]


class Fields5(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        str, Field(description="Field names must be unique within the table (case-insensitive).", min_length=1)
    ]
    description: Annotated[Optional[str], Field(max_length=20000)] = None
    type: Type5
    options: Options4


class Type6(Enum):
    DURATION = "duration"


class DurationFormat(Enum):
    """
    Display format for the duration value.
    """

    H_MM = "h:mm"
    H_MM_SS = "h:mm:ss"
    H_MM_SS_S = "h:mm:ss.S"
    H_MM_SS_SS = "h:mm:ss.SS"
    H_MM_SS_SSS = "h:mm:ss.SSS"


class Options5(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    durationFormat: Annotated[DurationFormat, Field(description="Display format for the duration value.")]


class Fields6(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        str, Field(description="Field names must be unique within the table (case-insensitive).", min_length=1)
    ]
    description: Annotated[Optional[str], Field(max_length=20000)] = None
    type: Type6
    options: Options5


class Type7(Enum):
    DATE = "date"


class Name(Enum):
    """
    Date format preset: "local" (l), "friendly" (LL), "us" (M/D/YYYY), "european" (D/M/YYYY), "iso" (YYYY-MM-DD).
    """

    LOCAL = "local"
    FRIENDLY = "friendly"
    US = "us"
    EUROPEAN = "european"
    ISO = "iso"


class Format(Enum):
    """
    Format is optional, but must match name if provided.
    """

    L = "l"
    LL = "LL"
    M_D_YYYY = "M/D/YYYY"
    D_M_YYYY = "D/M/YYYY"
    YYYY_MM_DD = "YYYY-MM-DD"


class DateFormat(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        Name,
        Field(
            description=(
                'Date format preset: "local" (l), "friendly" (LL), "us" (M/D/YYYY), "european" (D/M/YYYY), "iso"'
                " (YYYY-MM-DD)."
            )
        ),
    ]
    format: Annotated[Optional[Format], Field(description="Format is optional, but must match name if provided.")] = (
        None
    )


class Options6(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    dateFormat: DateFormat


class Fields7(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        str, Field(description="Field names must be unique within the table (case-insensitive).", min_length=1)
    ]
    description: Annotated[Optional[str], Field(max_length=20000)] = None
    type: Type7
    options: Options6


class Type8(Enum):
    DATE_TIME = "dateTime"


class DateFormat1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        Name,
        Field(
            description=(
                'Date format preset: "local" (l), "friendly" (LL), "us" (M/D/YYYY), "european" (D/M/YYYY), "iso"'
                " (YYYY-MM-DD)."
            )
        ),
    ]
    format: Annotated[Optional[Format], Field(description="Format is optional, but must match name if provided.")] = (
        None
    )


class Name2(Enum):
    """
    Time format preset: "12hour" (h:mma), "24hour" (HH:mm).
    """

    FIELD_12HOUR = "12hour"
    FIELD_24HOUR = "24hour"


class Format2(Enum):
    """
    Format is optional, but must match name if provided.
    """

    H_MMA = "h:mma"
    HH_MM = "HH:mm"


class TimeFormat(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[Name2, Field(description='Time format preset: "12hour" (h:mma), "24hour" (HH:mm).')]
    format: Annotated[Optional[Format2], Field(description="Format is optional, but must match name if provided.")] = (
        None
    )


class Options7(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    dateFormat: DateFormat1
    timeFormat: TimeFormat
    timeZone: Annotated[
        str,
        Field(
            description=(
                'IANA time zone identifier (e.g., "America/New_York", "Europe/London", "UTC"). Required for dateTime'
                " fields."
            )
        ),
    ]


class Fields8(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        str, Field(description="Field names must be unique within the table (case-insensitive).", min_length=1)
    ]
    description: Annotated[Optional[str], Field(max_length=20000)] = None
    type: Type8
    options: Options7


class Type9(Enum):
    RATING = "rating"


class Color2(Enum):
    """
    Rating color. Use "yellowBright" for a standard rating.
    """

    YELLOW_BRIGHT = "yellowBright"
    ORANGE_BRIGHT = "orangeBright"
    RED_BRIGHT = "redBright"
    PINK_BRIGHT = "pinkBright"
    PURPLE_BRIGHT = "purpleBright"
    BLUE_BRIGHT = "blueBright"
    CYAN_BRIGHT = "cyanBright"
    TEAL_BRIGHT = "tealBright"
    GREEN_BRIGHT = "greenBright"
    GRAY_BRIGHT = "grayBright"


class Icon1(Enum):
    """
    Rating icon. Use "star" for a standard rating.
    """

    STAR = "star"
    HEART = "heart"
    THUMBS_UP = "thumbsUp"
    FLAG = "flag"
    DOT = "dot"


class Options8(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    color: Annotated[Color2, Field(description='Rating color. Use "yellowBright" for a standard rating.')]
    icon: Annotated[Icon1, Field(description='Rating icon. Use "star" for a standard rating.')]
    max: Annotated[int, Field(ge=1, le=10)]


class Fields9(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        str, Field(description="Field names must be unique within the table (case-insensitive).", min_length=1)
    ]
    description: Annotated[Optional[str], Field(max_length=20000)] = None
    type: Type9
    options: Options8


class Type10(Enum):
    MULTIPLE_RECORD_LINKS = "multipleRecordLinks"


class Options9(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    linkedTableId: Annotated[
        str,
        Field(
            description="The ID of the table to link to. Use list_tables_for_base to get the table ID.",
            pattern="^tbl[A-Za-z0-9]{14}$",
        ),
    ]


class Fields10(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        str, Field(description="Field names must be unique within the table (case-insensitive).", min_length=1)
    ]
    description: Annotated[Optional[str], Field(max_length=20000)] = None
    type: Type10
    options: Options9


class Table1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        str, Field(description="Must be unique within the base (case-insensitive).", max_length=255, min_length=1)
    ]
    description: Annotated[Optional[str], Field(max_length=20000)] = None
    fields: Annotated[
        list[Union[Fields, Fields1, Fields2, Fields3, Fields4, Fields5, Fields6, Fields7, Fields8, Fields9, Fields10]],
        Field(
            description=(
                'The first field becomes the primary field and must be one of these types:\n"singleLineText", "email",'
                ' "url", "multilineText", "number", "percent",\n"currency", "duration", "date", "dateTime",'
                ' "phoneNumber", "barcode".\nRemaining fields can be any type.'
            ),
            min_length=1,
        ),
    ]


class CreateBaseInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    workspaceId: Annotated[
        str,
        Field(
            description=(
                'The ID of the workspace to create the base in.\nMust start with "wsp" and is 17 characters'
                ' long.\nExample: "wspZfrNIUEip5MazD".\nDo not substitute user-facing names for workspaceId.\nTo get'
                " workspaceId, use the list_workspaces tool."
            ),
            pattern="^wsp[A-Za-z0-9]{14}$",
        ),
    ]
    name: Annotated[str, Field(description="The name for the new base.", max_length=255, min_length=1)]
    tables: Annotated[
        Optional[list[Table1]],
        Field(
            description=(
                'Optional. The tables to create in the new base.\nIf omitted, a default table ("Table 1") with a "Name"'
                " singleLineText field is created."
            ),
            min_length=1,
        ),
    ] = None


class Type11(Enum):
    SINGLE_COLLABORATOR = "singleCollaborator"
    MULTIPLE_COLLABORATORS = "multipleCollaborators"
    SINGLE_LINE_TEXT = "singleLineText"
    EMAIL = "email"
    URL = "url"
    MULTILINE_TEXT = "multilineText"
    PHONE_NUMBER = "phoneNumber"
    RICH_TEXT = "richText"
    BARCODE = "barcode"
    MULTIPLE_ATTACHMENTS = "multipleAttachments"


class Fields11(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        str, Field(description="Field names must be unique within the table (case-insensitive).", min_length=1)
    ]
    description: Annotated[Optional[str], Field(max_length=20000)] = None
    type: Type11


class Type12(Enum):
    CHECKBOX = "checkbox"


class Icon2(Enum):
    """
    Checkbox icon. Use "check" for a standard checkbox.
    """

    CHECK = "check"
    X_CHECKBOX = "xCheckbox"
    STAR = "star"
    HEART = "heart"
    THUMBS_UP = "thumbsUp"
    FLAG = "flag"
    DOT = "dot"


class Color3(Enum):
    """
    Checkbox color. Use "greenBright" for a standard checkbox.
    """

    GREEN_BRIGHT = "greenBright"
    TEAL_BRIGHT = "tealBright"
    CYAN_BRIGHT = "cyanBright"
    BLUE_BRIGHT = "blueBright"
    PURPLE_BRIGHT = "purpleBright"
    PINK_BRIGHT = "pinkBright"
    RED_BRIGHT = "redBright"
    ORANGE_BRIGHT = "orangeBright"
    YELLOW_BRIGHT = "yellowBright"
    GRAY_BRIGHT = "grayBright"


class Options10(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    icon: Annotated[Icon2, Field(description='Checkbox icon. Use "check" for a standard checkbox.')]
    color: Annotated[Color3, Field(description='Checkbox color. Use "greenBright" for a standard checkbox.')]


class Fields12(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        str, Field(description="Field names must be unique within the table (case-insensitive).", min_length=1)
    ]
    description: Annotated[Optional[str], Field(max_length=20000)] = None
    type: Type12
    options: Options10


class Type13(Enum):
    SINGLE_SELECT = "singleSelect"
    MULTIPLE_SELECTS = "multipleSelects"


class Color4(Enum):
    """
    Colors are auto-assigned if omitted.
    """

    BLUE_LIGHT2 = "blueLight2"
    CYAN_LIGHT2 = "cyanLight2"
    TEAL_LIGHT2 = "tealLight2"
    GREEN_LIGHT2 = "greenLight2"
    YELLOW_LIGHT2 = "yellowLight2"
    ORANGE_LIGHT2 = "orangeLight2"
    RED_LIGHT2 = "redLight2"
    PINK_LIGHT2 = "pinkLight2"
    PURPLE_LIGHT2 = "purpleLight2"
    GRAY_LIGHT2 = "grayLight2"
    BLUE_LIGHT1 = "blueLight1"
    CYAN_LIGHT1 = "cyanLight1"
    TEAL_LIGHT1 = "tealLight1"
    GREEN_LIGHT1 = "greenLight1"
    YELLOW_LIGHT1 = "yellowLight1"
    ORANGE_LIGHT1 = "orangeLight1"
    RED_LIGHT1 = "redLight1"
    PINK_LIGHT1 = "pinkLight1"
    PURPLE_LIGHT1 = "purpleLight1"
    GRAY_LIGHT1 = "grayLight1"
    BLUE_BRIGHT = "blueBright"
    CYAN_BRIGHT = "cyanBright"
    TEAL_BRIGHT = "tealBright"
    GREEN_BRIGHT = "greenBright"
    YELLOW_BRIGHT = "yellowBright"
    ORANGE_BRIGHT = "orangeBright"
    RED_BRIGHT = "redBright"
    PINK_BRIGHT = "pinkBright"
    PURPLE_BRIGHT = "purpleBright"
    GRAY_BRIGHT = "grayBright"
    BLUE_DARK1 = "blueDark1"
    CYAN_DARK1 = "cyanDark1"
    TEAL_DARK1 = "tealDark1"
    GREEN_DARK1 = "greenDark1"
    YELLOW_DARK1 = "yellowDark1"
    ORANGE_DARK1 = "orangeDark1"
    RED_DARK1 = "redDark1"
    PINK_DARK1 = "pinkDark1"
    PURPLE_DARK1 = "purpleDark1"
    GRAY_DARK1 = "grayDark1"


class Choice1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: str
    color: Annotated[Optional[Color4], Field(description="Colors are auto-assigned if omitted.")] = None


class Options11(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    choices: Annotated[list[Choice1], Field(max_length=10000)]


class Fields13(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        str, Field(description="Field names must be unique within the table (case-insensitive).", min_length=1)
    ]
    description: Annotated[Optional[str], Field(max_length=20000)] = None
    type: Type13
    options: Options11


class Type14(Enum):
    NUMBER = "number"


class Options12(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    precision: Annotated[int, Field(description="Number of decimal places.", ge=0, le=8)]


class Fields14(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        str, Field(description="Field names must be unique within the table (case-insensitive).", min_length=1)
    ]
    description: Annotated[Optional[str], Field(max_length=20000)] = None
    type: Type14
    options: Options12


class Type15(Enum):
    PERCENT = "percent"


class Fields15(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        str, Field(description="Field names must be unique within the table (case-insensitive).", min_length=1)
    ]
    description: Annotated[Optional[str], Field(max_length=20000)] = None
    type: Type15
    options: Options12


class Type16(Enum):
    CURRENCY = "currency"


class Options14(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    precision: Annotated[int, Field(description="Number of decimal places.", ge=0, le=7)]
    symbol: Annotated[str, Field(description='Currency symbol, e.g. "$", "€", "£", "¥".', max_length=100)]


class Fields16(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        str, Field(description="Field names must be unique within the table (case-insensitive).", min_length=1)
    ]
    description: Annotated[Optional[str], Field(max_length=20000)] = None
    type: Type16
    options: Options14


class Type17(Enum):
    DURATION = "duration"


class Options15(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    durationFormat: Annotated[DurationFormat, Field(description="Display format for the duration value.")]


class Fields17(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        str, Field(description="Field names must be unique within the table (case-insensitive).", min_length=1)
    ]
    description: Annotated[Optional[str], Field(max_length=20000)] = None
    type: Type17
    options: Options15


class Type18(Enum):
    DATE = "date"


class Name3(Enum):
    """
    Date format preset: "local" (l), "friendly" (LL), "us" (M/D/YYYY), "european" (D/M/YYYY), "iso" (YYYY-MM-DD).
    """

    LOCAL = "local"
    FRIENDLY = "friendly"
    US = "us"
    EUROPEAN = "european"
    ISO = "iso"


class Format3(Enum):
    """
    Format is optional, but must match name if provided.
    """

    L = "l"
    LL = "LL"
    M_D_YYYY = "M/D/YYYY"
    D_M_YYYY = "D/M/YYYY"
    YYYY_MM_DD = "YYYY-MM-DD"


class DateFormat2(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        Name3,
        Field(
            description=(
                'Date format preset: "local" (l), "friendly" (LL), "us" (M/D/YYYY), "european" (D/M/YYYY), "iso"'
                " (YYYY-MM-DD)."
            )
        ),
    ]
    format: Annotated[Optional[Format3], Field(description="Format is optional, but must match name if provided.")] = (
        None
    )


class Options16(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    dateFormat: DateFormat2


class Fields18(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        str, Field(description="Field names must be unique within the table (case-insensitive).", min_length=1)
    ]
    description: Annotated[Optional[str], Field(max_length=20000)] = None
    type: Type18
    options: Options16


class Type19(Enum):
    DATE_TIME = "dateTime"


class DateFormat3(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        Name3,
        Field(
            description=(
                'Date format preset: "local" (l), "friendly" (LL), "us" (M/D/YYYY), "european" (D/M/YYYY), "iso"'
                " (YYYY-MM-DD)."
            )
        ),
    ]
    format: Annotated[Optional[Format3], Field(description="Format is optional, but must match name if provided.")] = (
        None
    )


class Name5(Enum):
    """
    Time format preset: "12hour" (h:mma), "24hour" (HH:mm).
    """

    FIELD_12HOUR = "12hour"
    FIELD_24HOUR = "24hour"


class Format5(Enum):
    """
    Format is optional, but must match name if provided.
    """

    H_MMA = "h:mma"
    HH_MM = "HH:mm"


class TimeFormat1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[Name5, Field(description='Time format preset: "12hour" (h:mma), "24hour" (HH:mm).')]
    format: Annotated[Optional[Format5], Field(description="Format is optional, but must match name if provided.")] = (
        None
    )


class Options17(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    dateFormat: DateFormat3
    timeFormat: TimeFormat1
    timeZone: Annotated[
        str,
        Field(
            description=(
                'IANA time zone identifier (e.g., "America/New_York", "Europe/London", "UTC"). Required for dateTime'
                " fields."
            )
        ),
    ]


class Fields19(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        str, Field(description="Field names must be unique within the table (case-insensitive).", min_length=1)
    ]
    description: Annotated[Optional[str], Field(max_length=20000)] = None
    type: Type19
    options: Options17


class Type20(Enum):
    RATING = "rating"


class Color5(Enum):
    """
    Rating color. Use "yellowBright" for a standard rating.
    """

    YELLOW_BRIGHT = "yellowBright"
    ORANGE_BRIGHT = "orangeBright"
    RED_BRIGHT = "redBright"
    PINK_BRIGHT = "pinkBright"
    PURPLE_BRIGHT = "purpleBright"
    BLUE_BRIGHT = "blueBright"
    CYAN_BRIGHT = "cyanBright"
    TEAL_BRIGHT = "tealBright"
    GREEN_BRIGHT = "greenBright"
    GRAY_BRIGHT = "grayBright"


class Icon3(Enum):
    """
    Rating icon. Use "star" for a standard rating.
    """

    STAR = "star"
    HEART = "heart"
    THUMBS_UP = "thumbsUp"
    FLAG = "flag"
    DOT = "dot"


class Options18(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    color: Annotated[Color5, Field(description='Rating color. Use "yellowBright" for a standard rating.')]
    icon: Annotated[Icon3, Field(description='Rating icon. Use "star" for a standard rating.')]
    max: Annotated[int, Field(ge=1, le=10)]


class Fields20(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        str, Field(description="Field names must be unique within the table (case-insensitive).", min_length=1)
    ]
    description: Annotated[Optional[str], Field(max_length=20000)] = None
    type: Type20
    options: Options18


class Type21(Enum):
    MULTIPLE_RECORD_LINKS = "multipleRecordLinks"


class Options19(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    linkedTableId: Annotated[
        str,
        Field(
            description="The ID of the table to link to. Use list_tables_for_base to get the table ID.",
            pattern="^tbl[A-Za-z0-9]{14}$",
        ),
    ]


class Fields21(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        str, Field(description="Field names must be unique within the table (case-insensitive).", min_length=1)
    ]
    description: Annotated[Optional[str], Field(max_length=20000)] = None
    type: Type21
    options: Options19


class CreateTableInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    baseId: Annotated[
        str,
        Field(
            description=(
                'The ID of the base to create the table in.\nMust start with "app" and is 17 characters long.\nExample:'
                ' "appZfrNIUEip5MazD".\nDo not substitute user-facing names for baseId.\nTo get baseId, use the'
                " search_bases or list_bases tool."
            ),
            pattern="^app[A-Za-z0-9]{14}$",
        ),
    ]
    name: Annotated[
        str, Field(description="Must be unique within the base (case-insensitive).", max_length=255, min_length=1)
    ]
    description: Annotated[Optional[str], Field(max_length=20000)] = None
    fields: Annotated[
        list[
            Union[
                Fields11,
                Fields12,
                Fields13,
                Fields14,
                Fields15,
                Fields16,
                Fields17,
                Fields18,
                Fields19,
                Fields20,
                Fields21,
            ]
        ],
        Field(
            description=(
                'The first field becomes the primary field and must be one of these types:\n"singleLineText", "email",'
                ' "url", "multilineText", "number", "percent",\n"currency", "duration", "date", "dateTime",'
                ' "phoneNumber", "barcode".\nRemaining fields can be any type.'
            ),
            min_length=1,
        ),
    ]


class UpdateTableInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    baseId: Annotated[
        str,
        Field(
            description=(
                'The ID of the base containing the table.\nMust start with "app" and is 17 characters long.\nExample:'
                ' "appZfrNIUEip5MazD".\nDo not substitute user-facing names for baseId.\nTo get baseId, use the'
                " search_bases or list_bases tool."
            ),
            pattern="^app[A-Za-z0-9]{14}$",
        ),
    ]
    tableId: Annotated[
        str,
        Field(
            description=(
                'The ID of the table to update.\nMust start with "tbl" and is 17 characters long.\nExample:'
                ' "tblGlReoTNWfYnXIG".\nDo not substitute user-facing names for tableId.\nTo get tableId, use the'
                " list_tables_for_base tool."
            ),
            pattern="^tbl[A-Za-z0-9]{14}$",
        ),
    ]
    name: Annotated[
        Optional[str],
        Field(
            description="The new name for the table. Must be unique within the base (case-insensitive).",
            max_length=255,
            min_length=1,
        ),
    ] = None
    description: Annotated[Optional[str], Field(max_length=20000)] = None


class Type22(Enum):
    SINGLE_COLLABORATOR = "singleCollaborator"
    MULTIPLE_COLLABORATORS = "multipleCollaborators"
    SINGLE_LINE_TEXT = "singleLineText"
    EMAIL = "email"
    URL = "url"
    MULTILINE_TEXT = "multilineText"
    PHONE_NUMBER = "phoneNumber"
    RICH_TEXT = "richText"
    BARCODE = "barcode"
    MULTIPLE_ATTACHMENTS = "multipleAttachments"


class FieldModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        str, Field(description="Field names must be unique within the table (case-insensitive).", min_length=1)
    ]
    description: Annotated[Optional[str], Field(max_length=20000)] = None
    type: Type22


class Type23(Enum):
    CHECKBOX = "checkbox"


class Icon4(Enum):
    """
    Checkbox icon. Use "check" for a standard checkbox.
    """

    CHECK = "check"
    X_CHECKBOX = "xCheckbox"
    STAR = "star"
    HEART = "heart"
    THUMBS_UP = "thumbsUp"
    FLAG = "flag"
    DOT = "dot"


class Color6(Enum):
    """
    Checkbox color. Use "greenBright" for a standard checkbox.
    """

    GREEN_BRIGHT = "greenBright"
    TEAL_BRIGHT = "tealBright"
    CYAN_BRIGHT = "cyanBright"
    BLUE_BRIGHT = "blueBright"
    PURPLE_BRIGHT = "purpleBright"
    PINK_BRIGHT = "pinkBright"
    RED_BRIGHT = "redBright"
    ORANGE_BRIGHT = "orangeBright"
    YELLOW_BRIGHT = "yellowBright"
    GRAY_BRIGHT = "grayBright"


class Options20(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    icon: Annotated[Icon4, Field(description='Checkbox icon. Use "check" for a standard checkbox.')]
    color: Annotated[Color6, Field(description='Checkbox color. Use "greenBright" for a standard checkbox.')]


class Field1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        str, Field(description="Field names must be unique within the table (case-insensitive).", min_length=1)
    ]
    description: Annotated[Optional[str], Field(max_length=20000)] = None
    type: Type23
    options: Options20


class Type24(Enum):
    SINGLE_SELECT = "singleSelect"
    MULTIPLE_SELECTS = "multipleSelects"


class Color7(Enum):
    """
    Colors are auto-assigned if omitted.
    """

    BLUE_LIGHT2 = "blueLight2"
    CYAN_LIGHT2 = "cyanLight2"
    TEAL_LIGHT2 = "tealLight2"
    GREEN_LIGHT2 = "greenLight2"
    YELLOW_LIGHT2 = "yellowLight2"
    ORANGE_LIGHT2 = "orangeLight2"
    RED_LIGHT2 = "redLight2"
    PINK_LIGHT2 = "pinkLight2"
    PURPLE_LIGHT2 = "purpleLight2"
    GRAY_LIGHT2 = "grayLight2"
    BLUE_LIGHT1 = "blueLight1"
    CYAN_LIGHT1 = "cyanLight1"
    TEAL_LIGHT1 = "tealLight1"
    GREEN_LIGHT1 = "greenLight1"
    YELLOW_LIGHT1 = "yellowLight1"
    ORANGE_LIGHT1 = "orangeLight1"
    RED_LIGHT1 = "redLight1"
    PINK_LIGHT1 = "pinkLight1"
    PURPLE_LIGHT1 = "purpleLight1"
    GRAY_LIGHT1 = "grayLight1"
    BLUE_BRIGHT = "blueBright"
    CYAN_BRIGHT = "cyanBright"
    TEAL_BRIGHT = "tealBright"
    GREEN_BRIGHT = "greenBright"
    YELLOW_BRIGHT = "yellowBright"
    ORANGE_BRIGHT = "orangeBright"
    RED_BRIGHT = "redBright"
    PINK_BRIGHT = "pinkBright"
    PURPLE_BRIGHT = "purpleBright"
    GRAY_BRIGHT = "grayBright"
    BLUE_DARK1 = "blueDark1"
    CYAN_DARK1 = "cyanDark1"
    TEAL_DARK1 = "tealDark1"
    GREEN_DARK1 = "greenDark1"
    YELLOW_DARK1 = "yellowDark1"
    ORANGE_DARK1 = "orangeDark1"
    RED_DARK1 = "redDark1"
    PINK_DARK1 = "pinkDark1"
    PURPLE_DARK1 = "purpleDark1"
    GRAY_DARK1 = "grayDark1"


class Choice2(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: str
    color: Annotated[Optional[Color7], Field(description="Colors are auto-assigned if omitted.")] = None


class Options21(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    choices: Annotated[list[Choice2], Field(max_length=10000)]


class Field2(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        str, Field(description="Field names must be unique within the table (case-insensitive).", min_length=1)
    ]
    description: Annotated[Optional[str], Field(max_length=20000)] = None
    type: Type24
    options: Options21


class Type25(Enum):
    NUMBER = "number"


class Options22(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    precision: Annotated[int, Field(description="Number of decimal places.", ge=0, le=8)]


class Field3(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        str, Field(description="Field names must be unique within the table (case-insensitive).", min_length=1)
    ]
    description: Annotated[Optional[str], Field(max_length=20000)] = None
    type: Type25
    options: Options22


class Type26(Enum):
    PERCENT = "percent"


class Field4(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        str, Field(description="Field names must be unique within the table (case-insensitive).", min_length=1)
    ]
    description: Annotated[Optional[str], Field(max_length=20000)] = None
    type: Type26
    options: Options22


class Type27(Enum):
    CURRENCY = "currency"


class Options24(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    precision: Annotated[int, Field(description="Number of decimal places.", ge=0, le=7)]
    symbol: Annotated[str, Field(description='Currency symbol, e.g. "$", "€", "£", "¥".', max_length=100)]


class Field5(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        str, Field(description="Field names must be unique within the table (case-insensitive).", min_length=1)
    ]
    description: Annotated[Optional[str], Field(max_length=20000)] = None
    type: Type27
    options: Options24


class Type28(Enum):
    DURATION = "duration"


class Options25(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    durationFormat: Annotated[DurationFormat, Field(description="Display format for the duration value.")]


class Field6(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        str, Field(description="Field names must be unique within the table (case-insensitive).", min_length=1)
    ]
    description: Annotated[Optional[str], Field(max_length=20000)] = None
    type: Type28
    options: Options25


class Type29(Enum):
    DATE = "date"


class Name6(Enum):
    """
    Date format preset: "local" (l), "friendly" (LL), "us" (M/D/YYYY), "european" (D/M/YYYY), "iso" (YYYY-MM-DD).
    """

    LOCAL = "local"
    FRIENDLY = "friendly"
    US = "us"
    EUROPEAN = "european"
    ISO = "iso"


class Format6(Enum):
    """
    Format is optional, but must match name if provided.
    """

    L = "l"
    LL = "LL"
    M_D_YYYY = "M/D/YYYY"
    D_M_YYYY = "D/M/YYYY"
    YYYY_MM_DD = "YYYY-MM-DD"


class DateFormat4(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        Name6,
        Field(
            description=(
                'Date format preset: "local" (l), "friendly" (LL), "us" (M/D/YYYY), "european" (D/M/YYYY), "iso"'
                " (YYYY-MM-DD)."
            )
        ),
    ]
    format: Annotated[Optional[Format6], Field(description="Format is optional, but must match name if provided.")] = (
        None
    )


class Options26(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    dateFormat: DateFormat4


class Field7(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        str, Field(description="Field names must be unique within the table (case-insensitive).", min_length=1)
    ]
    description: Annotated[Optional[str], Field(max_length=20000)] = None
    type: Type29
    options: Options26


class Type30(Enum):
    DATE_TIME = "dateTime"


class DateFormat5(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        Name6,
        Field(
            description=(
                'Date format preset: "local" (l), "friendly" (LL), "us" (M/D/YYYY), "european" (D/M/YYYY), "iso"'
                " (YYYY-MM-DD)."
            )
        ),
    ]
    format: Annotated[Optional[Format6], Field(description="Format is optional, but must match name if provided.")] = (
        None
    )


class Name8(Enum):
    """
    Time format preset: "12hour" (h:mma), "24hour" (HH:mm).
    """

    FIELD_12HOUR = "12hour"
    FIELD_24HOUR = "24hour"


class Format8(Enum):
    """
    Format is optional, but must match name if provided.
    """

    H_MMA = "h:mma"
    HH_MM = "HH:mm"


class TimeFormat2(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[Name8, Field(description='Time format preset: "12hour" (h:mma), "24hour" (HH:mm).')]
    format: Annotated[Optional[Format8], Field(description="Format is optional, but must match name if provided.")] = (
        None
    )


class Options27(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    dateFormat: DateFormat5
    timeFormat: TimeFormat2
    timeZone: Annotated[
        str,
        Field(
            description=(
                'IANA time zone identifier (e.g., "America/New_York", "Europe/London", "UTC"). Required for dateTime'
                " fields."
            )
        ),
    ]


class Field8(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        str, Field(description="Field names must be unique within the table (case-insensitive).", min_length=1)
    ]
    description: Annotated[Optional[str], Field(max_length=20000)] = None
    type: Type30
    options: Options27


class Type31(Enum):
    RATING = "rating"


class Color8(Enum):
    """
    Rating color. Use "yellowBright" for a standard rating.
    """

    YELLOW_BRIGHT = "yellowBright"
    ORANGE_BRIGHT = "orangeBright"
    RED_BRIGHT = "redBright"
    PINK_BRIGHT = "pinkBright"
    PURPLE_BRIGHT = "purpleBright"
    BLUE_BRIGHT = "blueBright"
    CYAN_BRIGHT = "cyanBright"
    TEAL_BRIGHT = "tealBright"
    GREEN_BRIGHT = "greenBright"
    GRAY_BRIGHT = "grayBright"


class Icon5(Enum):
    """
    Rating icon. Use "star" for a standard rating.
    """

    STAR = "star"
    HEART = "heart"
    THUMBS_UP = "thumbsUp"
    FLAG = "flag"
    DOT = "dot"


class Options28(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    color: Annotated[Color8, Field(description='Rating color. Use "yellowBright" for a standard rating.')]
    icon: Annotated[Icon5, Field(description='Rating icon. Use "star" for a standard rating.')]
    max: Annotated[int, Field(ge=1, le=10)]


class Field9(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        str, Field(description="Field names must be unique within the table (case-insensitive).", min_length=1)
    ]
    description: Annotated[Optional[str], Field(max_length=20000)] = None
    type: Type31
    options: Options28


class Type32(Enum):
    MULTIPLE_RECORD_LINKS = "multipleRecordLinks"


class Options29(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    linkedTableId: Annotated[
        str,
        Field(
            description="The ID of the table to link to. Use list_tables_for_base to get the table ID.",
            pattern="^tbl[A-Za-z0-9]{14}$",
        ),
    ]


class Field10(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        str, Field(description="Field names must be unique within the table (case-insensitive).", min_length=1)
    ]
    description: Annotated[Optional[str], Field(max_length=20000)] = None
    type: Type32
    options: Options29


class Type33(Enum):
    FORMULA = "formula"


class Options30(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    formula: Annotated[
        str,
        Field(
            description=(
                "The formula expression. Reference fields by name ({Field Name}) or ID ({fldXXXXXXXXXXXXXX}). Use"
                " get_table_schema to discover available field names."
            ),
            min_length=1,
        ),
    ]


class Field11(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        str, Field(description="Field names must be unique within the table (case-insensitive).", min_length=1)
    ]
    description: Annotated[Optional[str], Field(max_length=20000)] = None
    type: Type33
    options: Options30


class CreateFieldInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    baseId: Annotated[
        str,
        Field(
            description=(
                'The ID of the base containing the table.\nMust start with "app" and is 17 characters long.\nExample:'
                ' "appZfrNIUEip5MazD".\nDo not substitute user-facing names for baseId.\nTo get baseId, use the'
                " search_bases or list_bases tool."
            ),
            pattern="^app[A-Za-z0-9]{14}$",
        ),
    ]
    tableId: Annotated[
        str,
        Field(
            description=(
                'The ID of the table to create the field in.\nMust start with "tbl" and is 17 characters'
                ' long.\nExample: "tblGlReoTNWfYnXIG".\nDo not substitute user-facing names for tableId.\nTo get'
                " tableId, use the list_tables_for_base tool."
            ),
            pattern="^tbl[A-Za-z0-9]{14}$",
        ),
    ]
    field: Union[FieldModel, Field1, Field2, Field3, Field4, Field5, Field6, Field7, Field8, Field9, Field10, Field11]


class Options31(BaseModel):
    """
    Type-specific field options.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    formula: Annotated[
        Optional[str],
        Field(
            description=(
                "The new formula expression (formula fields only). Reference fields by name ({Field Name}) or ID"
                " ({fldXXXXXXXXXXXXXX})."
            ),
            min_length=1,
        ),
    ] = None


class UpdateFieldInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    baseId: Annotated[
        str,
        Field(
            description=(
                'The ID of the base containing the table.\nMust start with "app" and is 17 characters long.\nExample:'
                ' "appZfrNIUEip5MazD".\nDo not substitute user-facing names for baseId.\nTo get baseId, use the'
                " search_bases or list_bases tool."
            ),
            pattern="^app[A-Za-z0-9]{14}$",
        ),
    ]
    tableId: Annotated[
        str,
        Field(
            description=(
                'The ID of the table containing the field.\nMust start with "tbl" and is 17 characters long.\nExample:'
                ' "tblGlReoTNWfYnXIG".\nDo not substitute user-facing names for tableId.\nTo get tableId, use the'
                " list_tables_for_base tool."
            ),
            pattern="^tbl[A-Za-z0-9]{14}$",
        ),
    ]
    fieldId: Annotated[
        str,
        Field(
            description=(
                'The ID of the field to update.\nField IDs must start with "fld" and is 17 characters long.\nExample:'
                ' "fldGlRtkBNWfYnPOV".\nDo not substitute user-facing names for IDs.\nTo get fieldId, use the'
                " list_tables_for_base tool."
            ),
            pattern="^fld[A-Za-z0-9]{14}$",
        ),
    ]
    name: Annotated[
        Optional[str],
        Field(
            description="The new name for the field. Must be unique within the table (case-insensitive).",
            max_length=255,
            min_length=1,
        ),
    ] = None
    description: Annotated[Optional[str], Field(max_length=20000)] = None
    options: Annotated[Optional[Options31], Field(description="Type-specific field options.")] = None


class Operator2(Enum):
    """
    The operator to use to combine the operands (filter conditions).
    Acceptable values are 'and' and 'or'.
    The default operator is 'and'.
    """

    AND = "and"
    OR = "or"


class Operator3(Enum):
    """
    The comparison operator for this filter condition, applied to the operands. Acceptable values are =, !=, <, >,
    <=, >=, hasAnyOf, hasAllOf, isWithin, isAnyOf, isNoneOf, contains, doesNotContain, filename, fileType, isEmpty,
    isNotEmpty. For singleSelect and singleCollaborator fields, use =, !=, isAnyOf, or isNoneOf. For multipleSelects
    and multipleCollaborators fields, use hasAnyOf, hasAllOf, =, or doesNotContain.
    """

    FIELD_ = "="
    FIELD__ = "!="
    field__1 = "<"
    field__2 = ">"
    field___1 = "<="
    field___2 = ">="
    HAS_ANY_OF = "hasAnyOf"
    HAS_ALL_OF = "hasAllOf"
    IS_WITHIN = "isWithin"
    IS_ANY_OF = "isAnyOf"
    IS_NONE_OF = "isNoneOf"
    CONTAINS = "contains"
    DOES_NOT_CONTAIN = "doesNotContain"
    FILENAME = "filename"
    FILE_TYPE = "fileType"
    IS_EMPTY = "isEmpty"
    IS_NOT_EMPTY = "isNotEmpty"


class Operands7(RootModel[str]):
    root: Annotated[str, Field(pattern="^fld[A-Za-z0-9]{14}$")]


class Operands8(Enum):
    IMAGE = "image"
    TEXT = "text"


class Mode5(Enum):
    TODAY = "today"
    TOMORROW = "tomorrow"
    YESTERDAY = "yesterday"
    ONE_WEEK_AGO = "oneWeekAgo"
    ONE_WEEK_FROM_NOW = "oneWeekFromNow"
    ONE_MONTH_AGO = "oneMonthAgo"
    ONE_MONTH_FROM_NOW = "oneMonthFromNow"


class Operands9(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    mode: Mode5
    timeZone: Annotated[str, Field(description='IANA time zone identifier (e.g., "America/New_York").')]


class Mode6(Enum):
    EXACT_DATE = "exactDate"


class Operands10(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    mode: Mode6
    exactDate: str
    timeZone: Annotated[str, Field(description='IANA time zone identifier (e.g., "America/New_York").')]


class Mode7(Enum):
    DAYS_AGO = "daysAgo"
    DAYS_FROM_NOW = "daysFromNow"


class Operands11(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    mode: Mode7
    numberOfDays: Annotated[int, Field(ge=0)]
    timeZone: Annotated[str, Field(description='IANA time zone identifier (e.g., "America/New_York").')]


class Mode8(Enum):
    PAST_WEEK = "pastWeek"
    PAST_MONTH = "pastMonth"
    PAST_YEAR = "pastYear"
    NEXT_WEEK = "nextWeek"
    NEXT_MONTH = "nextMonth"
    NEXT_YEAR = "nextYear"
    THIS_WEEK_TO_DATE = "thisWeekToDate"
    THIS_MONTH_TO_DATE = "thisMonthToDate"
    THIS_YEAR_TO_DATE = "thisYearToDate"
    THIS_CALENDAR_WEEK = "thisCalendarWeek"
    THIS_CALENDAR_MONTH = "thisCalendarMonth"
    THIS_CALENDAR_YEAR = "thisCalendarYear"


class Operands12(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    mode: Mode8
    timeZone: Annotated[str, Field(description='IANA time zone identifier (e.g., "America/New_York").')]


class Mode9(Enum):
    NEXT_NUMBER_OF_DAYS = "nextNumberOfDays"
    PAST_NUMBER_OF_DAYS = "pastNumberOfDays"


class Operands13(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    mode: Mode9
    numberOfDays: Annotated[int, Field(ge=0)]
    timeZone: Annotated[str, Field(description='IANA time zone identifier (e.g., "America/New_York").')]


class Operand1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    operator: Annotated[
        Operator3,
        Field(
            description=(
                "The comparison operator for this filter condition, applied to the operands.\nAcceptable values are =,"
                " !=, <, >, <=, >=, hasAnyOf, hasAllOf, isWithin, isAnyOf, isNoneOf, contains, doesNotContain,"
                " filename, fileType, isEmpty, isNotEmpty.\nFor singleSelect and singleCollaborator fields, use =, !=,"
                " isAnyOf, or isNoneOf.\nFor multipleSelects and multipleCollaborators fields, use hasAnyOf, hasAllOf,"
                " =, or doesNotContain."
            )
        ),
    ]
    operands: Annotated[
        list[
            Union[
                Operands7,
                Optional[
                    Union[
                        str,
                        float,
                        bool,
                        list[str],
                        Operands8,
                        Union[Operands9, Operands10, Operands11],
                        Union[Operands12, Operands13],
                    ]
                ],
            ]
        ],
        Field(
            description=(
                "The operands (arguments) to the comparison operator.\nThe first operand must be a field ID. Example:"
                ' "fld9x4rqyBSCLzsJM". Do not substitute user-facing names for IDs.\nThe second operand depends on the'
                " operator and field type:\n    - isEmpty, isNotEmpty: No second operand (use a single-element array"
                " with just the field ID).\n    - =, !=, contains, doesNotContain: A string for text fields, a number"
                " for number fields, a boolean for checkbox fields.\n    - <, >, <=, >=: A number.\n    - For"
                " singleSelect/multipleSelects fields: The second operand must be a choice ID (e.g.,"
                ' "selABCDEFGHIJKLM") obtained from get_table_schema, not the choice\n    name.\n    - hasAnyOf,'
                " hasAllOf, isAnyOf, isNoneOf, doesNotContain: An array of strings (e.g., choice IDs for select fields,"
                " collaborator IDs for collaborator fields).\n    - For date/datetime fields with =, !=, <, >, <=, >=:"
                ' The second operand is a date value object, e.g. {"mode": "today", "timeZone": "America/New_York"},'
                ' {"mode": "exactDate",\n    "exactDate": "2024-01-15", "timeZone": "America/New_York"}, or {"mode":'
                ' "daysAgo", "numberOfDays": 7, "timeZone": "America/New_York"}.\n    - isWithin (date fields only):'
                ' The second operand is a date range object, e.g. {"mode": "pastWeek", "timeZone": "America/New_York"},'
                ' {"mode": "pastNumberOfDays", "numberOfDays":\n    30, "timeZone": "America/New_York"}.\n    -'
                ' filename: A string to match against attachment filenames.\n    - fileType: Either "image" or'
                ' "text".\nFor singleSelect/multipleSelects fields, the second operand must be a choice ID (e.g.,'
                ' "selet1KAKDTOhXQJk") obtained from get_table_schema.'
            ),
            max_length=2,
            min_length=1,
        ),
    ]
    operatorOptions: Optional[OperatorOptions] = None


class Filters1(BaseModel):
    """
    Additional filters to apply on top of the page element's built-in filters. These are combined with the element's
    static filters using AND. For hierarchy pages, filters apply only to the source level's table. Related levels may
    be constrained indirectly through the hierarchy's foreign key relationships. Describes the filters to apply to
    the records using a structured format. Example filter where the value of the field with ID "fld8WsrpLHHevsnW8" is
    "orange" or the value of the field with ID "fldulcCPDVz87Bmnw" is greater than 5: {"operator": "or", "operands":
    [{"operator": "=", "operands": ["fld8WsrpLHHevsnW8", "orange"]}, {"operator": ">", "operands": [
    "fldulcCPDVz87Bmnw", 5]}]} Example filter where the value of the collaborator field with ID "fldCRi9oz2vRLcIWr"
    can be any user in a group with ID "ugpDUVUnftA7H9bG8" and the value of the field with ID "fldgD18XtsueoiguT"
    equals select option with ID "selha8nGNAT5ATR7P": {"operator": "and", "operands": [{"operator": "hasAnyOf",
    "operands": ["fldCRi9oz2vRLcIWr", "ugpDUVUnftA7H9bG8"], "operatorOptions": {"matchGroupsByMembership": true}},
    {"operator": "=", "operands": ["fldgD18XtsueoiguT", "selha8nGNAT5ATR7P"]}]} Example filter for records where a
    date field is within the past week: {"operands": [{"operator": "isWithin", "operands": ["fldABC12345678x",
    {"mode": "pastWeek", "timeZone": "America/New_York"}]}]} Example filter for records where a field is not empty: {
    "operands": [{"operator": "isNotEmpty", "operands": ["fldABC12345678x"]}]}
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    operator: Annotated[
        Optional[Operator2],
        Field(
            description=(
                "The operator to use to combine the operands (filter conditions).\nAcceptable values are 'and' and"
                " 'or'.\nThe default operator is 'and'."
            )
        ),
    ] = None
    operands: Annotated[
        list[Operand1],
        Field(
            description=(
                "A list of filter conditions to apply to the records. These are combined using the top-level operator"
                ' (default "and").\nEach filter condition must have an "operator" key (the comparison operator, e.g.'
                ' "=", "contains", "isEmpty", etc) and an "operands" key (an array where\nthe first element is a field'
                ' ID and the optional second element is the value to compare against).\nExample: [{"operator":'
                ' "contains", "operands": ["fld9x4rqyBSCLzsJM", "apple"]}]'
            ),
            max_length=50,
            min_length=1,
        ),
    ]


class ListRecordsForPageInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    baseId: Annotated[
        str,
        Field(
            description=(
                'The ID of the base (application) containing the page.\nMust start with "app" and is 17 characters'
                ' long.\nExample: "appZfrNIUEip5MazD".\nDo not substitute user-facing names for baseId.\nTo get baseId,'
                " use the search_bases or list_bases tool."
            ),
            pattern="^app[A-Za-z0-9]{14}$",
        ),
    ]
    pageId: Annotated[
        str,
        Field(
            description=(
                'The ID of the interface page to read records from.\nMust start with "pag" and is 17 characters'
                ' long.\nExample: "pagXxYyZzAaBbCcDd".'
            ),
            pattern="^pag[A-Za-z0-9]{14}$",
        ),
    ]
    interfaceId: Annotated[
        str,
        Field(
            description=(
                'The ID of the interface that contains the page.\nMust start with "pbd" and is 17 characters long.'
            ),
            pattern="^pbd[A-Za-z0-9]{14}$",
        ),
    ]
    elementId: Annotated[
        Optional[str],
        Field(
            description=(
                "The ID of a specific element to query records for.\nRequired for dashboard pages. Obtain element IDs"
                ' from the dashboardElements\narray in the list_pages_for_base response.\nMust start with "pel" and is'
                " 17 characters long."
            ),
            pattern="^pel[A-Za-z0-9]{14}$",
        ),
    ] = None
    fieldIds: Annotated[
        Optional[list[FieldId2]],
        Field(
            description=(
                "Only data for fields whose IDs are in this list will be included in the result.\nPass in only the"
                " fields most useful for the user to see.\nIf not provided, the fields visible in the page element's"
                " visualization will be returned.\nFor hierarchy pages, field IDs are matched against each table — a"
                " field belonging to\nthe projects table will filter the projects records, and one belonging to the"
                " tasks\ntable will filter the tasks records. You can mix field IDs from different tables.\nField IDs"
                ' must start with "fld" and is 17 characters long.\nExample: "fldGlRtkBNWfYnPOV".\nDo not substitute'
                " user-facing names for IDs.\nTo get fieldId, use the list_tables_for_base tool."
            )
        ),
    ] = None
    pageSize: Annotated[
        Optional[int],
        Field(
            description=(
                "The maximum number of records to return in the response.\nThe server may respond with fewer records"
                " than this value when the total set has fewer records than this value."
            ),
            gt=0,
            le=1000,
        ),
    ] = None
    filters: Annotated[
        Optional[Filters1],
        Field(
            description=(
                "Additional filters to apply on top of the page element's built-in filters.\nThese are combined with"
                " the element's static filters using AND.\nFor hierarchy pages, filters apply only to the source"
                " level's table. Related levels\nmay be constrained indirectly through the hierarchy's foreign key"
                " relationships.\nDescribes the filters to apply to the records using a structured format.\nExample"
                ' filter where the value of the field with ID "fld8WsrpLHHevsnW8" is "orange" or the value of the field'
                ' with ID "fldulcCPDVz87Bmnw" is greater than 5:\n{"operator": "or", "operands": [{"operator": "=",'
                ' "operands": ["fld8WsrpLHHevsnW8", "orange"]}, {"operator": ">", "operands": ["fldulcCPDVz87Bmnw",'
                ' 5]}]}\nExample filter where the value of the collaborator field with ID "fldCRi9oz2vRLcIWr" can be'
                ' any user in a group with ID "ugpDUVUnftA7H9bG8" and the value of the field with ID'
                ' "fldgD18XtsueoiguT" equals select option with ID "selha8nGNAT5ATR7P":\n{"operator": "and",'
                ' "operands": [{"operator": "hasAnyOf", "operands": ["fldCRi9oz2vRLcIWr", "ugpDUVUnftA7H9bG8"],'
                ' "operatorOptions": {"matchGroupsByMembership": true}}, {"operator": "=", "operands":'
                ' ["fldgD18XtsueoiguT", "selha8nGNAT5ATR7P"]}]}\nExample filter for records where a date field is'
                ' within the past week:\n{"operands": [{"operator": "isWithin", "operands": ["fldABC12345678x",'
                ' {"mode": "pastWeek", "timeZone": "America/New_York"}]}]}\nExample filter for records where a field is'
                ' not empty:\n{"operands": [{"operator": "isNotEmpty", "operands": ["fldABC12345678x"]}]}'
            )
        ),
    ] = None


class ListPagesForBaseInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    baseId: Annotated[
        str,
        Field(
            description=(
                'The ID of the base to list pages from.\nMust start with "app" and is 17 characters long.\nExample:'
                ' "appZfrNIUEip5MazD".\nDo not substitute user-facing names for baseId.\nTo get baseId, use the'
                " search_bases or list_bases tool."
            ),
            pattern="^app[A-Za-z0-9]{14}$",
        ),
    ]


class Root(BaseModel):
    """
    The page and starting record. Set once from list_records_for_page results;
    stays the same as edges are appended.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    pageId: Annotated[
        str,
        Field(
            description=(
                'The page where the record was listed.\nMust start with "pag" and is 17 characters long.\nExample:'
                ' "pagXxYyZzAaBbCcDd".'
            ),
            pattern="^pag[A-Za-z0-9]{14}$",
        ),
    ]
    recordId: Annotated[
        str,
        Field(
            description=(
                "A record from list_records_for_page results. With no edges, this is\nthe record returned. With edges,"
                ' this is the starting point of the navigation.\nMust start with "rec" and is 17 characters'
                ' long.\nExample: "recZOTa3BDHxlJNzf".\nDo not substitute user-facing names for IDs\nTo get recordId,'
                " use the list_records_for_table tool or display_records_for_table tools."
            ),
            pattern="^rec[A-Za-z0-9]{14}$",
        ),
    ]
    elementId: Annotated[
        Optional[str],
        Field(
            description=(
                "The ID of the dashboard element to query. Required for dashboard pages.\nObtain element IDs from the"
                ' dashboardElements array in the\nlist_pages_for_base response.\nMust start with "pel" and is 17'
                " characters long."
            ),
            pattern="^pel[A-Za-z0-9]{14}$",
        ),
    ] = None


class Edge(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    fieldId: Annotated[
        str,
        Field(
            description=(
                'The linked record field used to traverse to the detail page.\nField IDs must start with "fld" and is'
                ' 17 characters long.\nExample: "fldGlRtkBNWfYnPOV".\nDo not substitute user-facing names for IDs.\nTo'
                " get fieldId, use the list_tables_for_base tool."
            ),
            pattern="^fld[A-Za-z0-9]{14}$",
        ),
    ]
    linkedRecordId: Annotated[
        str,
        Field(
            description=(
                'The record to navigate to by following the linked record field.\nMust start with "rec" and is 17'
                ' characters long.\nExample: "recZOTa3BDHxlJNzf".\nDo not substitute user-facing names for IDs\nTo get'
                " recordId, use the list_records_for_table tool or display_records_for_table tools."
            ),
            pattern="^rec[A-Za-z0-9]{14}$",
        ),
    ]


class Path(BaseModel):
    """
    The navigation path from the page where the record was listed.
    Construct the root from the same pageId used in list_records_for_page.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    root: Annotated[
        Root,
        Field(
            description=(
                "The page and starting record. Set once from list_records_for_page results;\nstays the same as edges"
                " are appended."
            )
        ),
    ]
    edges: Annotated[
        list[Edge],
        Field(
            description=(
                "Linked record traversals leading to the target record.\nEmpty array if the record is directly listed"
                " on the root page."
            )
        ),
    ]


class GetRecordForPageInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    baseId: Annotated[
        str,
        Field(
            description=(
                'The ID of the base (application) containing the page.\nMust start with "app" and is 17 characters'
                ' long.\nExample: "appZfrNIUEip5MazD".\nDo not substitute user-facing names for baseId.\nTo get baseId,'
                " use the search_bases or list_bases tool."
            ),
            pattern="^app[A-Za-z0-9]{14}$",
        ),
    ]
    interfaceId: Annotated[
        str,
        Field(
            description=(
                'The ID of the interface that contains the page.\nMust start with "pbd" and is 17 characters long.'
            ),
            pattern="^pbd[A-Za-z0-9]{14}$",
        ),
    ]
    path: Annotated[
        Path,
        Field(
            description=(
                "The navigation path from the page where the record was listed.\nConstruct the root from the same"
                " pageId used in list_records_for_page."
            )
        ),
    ]
    fieldIds: Annotated[
        Optional[list[FieldId2]],
        Field(
            description=(
                "Only data for fields whose IDs are in this list will be included in the result.\nIf not provided, all"
                ' fields visible on the page will be returned.\nField IDs must start with "fld" and is 17 characters'
                ' long.\nExample: "fldGlRtkBNWfYnPOV".\nDo not substitute user-facing names for IDs.\nTo get fieldId,'
                " use the list_tables_for_base tool."
            )
        ),
    ] = None


class SearchRecordsInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    baseId: Annotated[
        str,
        Field(
            description=(
                'The ID of the base containing the table.\nMust start with "app" and is 17 characters long.\nExample:'
                ' "appZfrNIUEip5MazD".\nDo not substitute user-facing names for baseId.\nTo get baseId, use the'
                " search_bases or list_bases tool."
            ),
            pattern="^app[A-Za-z0-9]{14}$",
        ),
    ]
    table: Annotated[
        str,
        Field(
            description=(
                'The table to search. Accepts either a table ID (e.g., "tblGlReoTNWfYnXIG") or a table name (e.g.,'
                ' "Orders"). Names are resolved case-insensitively within the base.'
            )
        ),
    ]
    query: Annotated[
        str,
        Field(
            description=(
                'The search query. Matches are case-insensitive and term-order independent. Examples: "acme" matches'
                ' "Acme Corp", "john smith" matches "Smith, John", ""Q1 Report"" (quoted) matches the exact phrase'
                " only."
            )
        ),
    ]
    fields: Annotated[
        Union[list[str], Literal["ALL_SEARCHABLE_FIELDS"]],
        Field(
            description=(
                "The fields to search over. Either pass an array of field IDs/names, or the literal string"
                ' "ALL_SEARCHABLE_FIELDS" to search across all searchable fields in the table. Field IDs look like'
                ' "fldGlRtkBNWfYnPOV". Field names (e.g., "Status") are resolved case-insensitively. Note: Not all'
                " field types are searchable. If this fails, fallback to using the list_records_for_table tool instead."
            )
        ),
    ]


class CreateInterfaceInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    baseId: Annotated[
        str,
        Field(
            description=(
                'The ID of the base in which to create the interface.\nMust start with "app" and is 17 characters'
                ' long.\nExample: "appZfrNIUEip5MazD".\nDo not substitute user-facing names for baseId.\nTo get baseId,'
                " use the search_bases or list_bases tool."
            ),
            pattern="^app[A-Za-z0-9]{14}$",
        ),
    ]
    name: Annotated[str, Field(description="The display name for the new interface.", max_length=255, min_length=1)]


class PageType(Enum):
    """
    The type of page to create.
    """

    VISUALIZATION = "visualization"
    DASHBOARD = "dashboard"
    CUSTOM_ELEMENT = "customElement"


class CreatePageInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    baseId: Annotated[
        str,
        Field(
            description=(
                'The ID of the base in which to create the page.\nMust start with "app" and is 17 characters'
                ' long.\nExample: "appZfrNIUEip5MazD".\nDo not substitute user-facing names for baseId.\nTo get baseId,'
                " use the search_bases or list_bases tool."
            ),
            pattern="^app[A-Za-z0-9]{14}$",
        ),
    ]
    interfaceId: Annotated[
        str,
        Field(
            description=(
                'The ID of the interface in which to create the page.\nMust start with "pbd" and is 17 characters long.'
            ),
            pattern="^pbd[A-Za-z0-9]{14}$",
        ),
    ]
    name: Annotated[str, Field(description="The display name for the new page.", max_length=255, min_length=1)]
    pageType: Annotated[PageType, Field(description="The type of page to create.")]
    pageConfiguration: Annotated[
        dict[str, Any],
        Field(
            description=(
                "Page type-specific configuration. Schema is provided by describe_page_type\nand describe_page_element."
            )
        ),
    ]


class DeletePageInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    baseId: Annotated[
        str,
        Field(
            description=(
                'The ID of the base containing the page to delete.\nMust start with "app" and is 17 characters'
                ' long.\nExample: "appZfrNIUEip5MazD".\nDo not substitute user-facing names for baseId.\nTo get baseId,'
                " use the search_bases or list_bases tool."
            ),
            pattern="^app[A-Za-z0-9]{14}$",
        ),
    ]
    pageId: Annotated[
        str,
        Field(
            description=(
                'The ID of the page to delete.\nMust start with "pag" and is 17 characters long.\nExample:'
                ' "pagXxYyZzAaBbCcDd".'
            ),
            pattern="^pag[A-Za-z0-9]{14}$",
        ),
    ]


class PageType1(Enum):
    """
    The page type to get the config schema for.
    """

    VISUALIZATION = "visualization"
    DASHBOARD = "dashboard"
    CUSTOM_ELEMENT = "customElement"


class DescribePageTypeInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    pageType: Annotated[PageType1, Field(description="The page type to get the config schema for.")]


class ElementType(Enum):
    """
    The page element type to get the config schema for.
    """

    KANBAN = "kanban"
    LIST = "list"
    CALENDAR = "calendar"
    GALLERY = "gallery"
    GRID = "grid"
    TIMELINE = "timeline"
    NUMBER = "number"
    BAR_CHART = "barChart"
    LINE_CHART = "lineChart"
    SCATTER_CHART = "scatterChart"
    PIE_CHART = "pieChart"
    DONUT_CHART = "donutChart"
    PIVOT_TABLE = "pivotTable"


class DescribePageElementInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    elementType: Annotated[ElementType, Field(description="The page element type to get the config schema for.")]


class PublishInterfaceInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    baseId: Annotated[
        str,
        Field(
            description=(
                'The ID of the base containing the interface.\nMust start with "app" and is 17 characters'
                ' long.\nExample: "appZfrNIUEip5MazD".\nDo not substitute user-facing names for baseId.\nTo get baseId,'
                " use the search_bases or list_bases tool."
            ),
            pattern="^app[A-Za-z0-9]{14}$",
        ),
    ]
    interfaceId: Annotated[
        str,
        Field(
            description='The ID of the interface to publish.\nMust start with "pbd" and is 17 characters long.',
            pattern="^pbd[A-Za-z0-9]{14}$",
        ),
    ]
