"""
Auto-generated Pydantic models for google-calendar's MCP. Supported tools are:

Example BoundMCPAgentConfig (JSON) for this provider:
 {
   "server": {
     "type": "http",
     "url": "https://calendarmcp.googleapis.com/mcp/v1"
   },
   "tools": [
     {
       "name": "list_events",
       "input_class_name": "rustic_ai.mcp.connectors.google-calendar.ListEventsInput",
       "description": "Lists calendar events in a given calendar satisfying the given conditions.\n\nKey Features:\n\n * Any Calendar ID, which can be user's primary calendar or others.\n * Time range filtering.\n * Retrieves ALL events matching the time constraints.\n\nIf available, use search_events tool instead for searches on the user's primary calendar if:\n\n * You are querying for events matching a specific topic, category, or intent (e.g., 'lunch meetings', 'project syncs').\n * You need to find the (top K) most relevant events rather than all events satisfying the constraints.\n * You need keyword or semantic search capabilities.\n\nUse this tool for queries like:\n\n * What's on my calendar tomorrow?\n * What's on my calendar for July 14th 2025?\n * What are my meetings next week?\n * Do I have any conflicts this afternoon?\n\n * What meetings does John have tomorrow?\n\nExample:\n\n    list_events(\n        startTime='2024-09-17T06:00:00',\n        endTime='2024-09-17T12:00:00',\n        pageSize=10\n    )\n    # Returns up to 10 calendar events between 6:00 AM and 12:00 PM on September 17, 2024 from the user's primary calendar.\n"
     },
     {
       "name": "get_event",
       "input_class_name": "rustic_ai.mcp.connectors.google-calendar.GetEventInput",
       "description": "Returns a single event from a given calendar.\n\nUse this tool for queries like:\n\n * Get details for the team meeting.\n * Show me the event with id event123 on my calendar.\n\nExample:\n\n    get_event(\n        eventId='event123'\n    )\n    # Returns the event details for the event with id `event123` on the user's primary calendar.\n"
     },
     {
       "name": "list_calendars",
       "input_class_name": "rustic_ai.mcp.connectors.google-calendar.ListCalendarsInput",
       "description": "Returns the calendars on the user's calendar list.\n\nUse this tool for queries like:\n\n * What are all my calendars?\n\nExample:\n\n    list_calendars()\n    # Returns all calendars the authenticated user has access to.\n"
     },
     {
       "name": "suggest_time",
       "input_class_name": "rustic_ai.mcp.connectors.google-calendar.SuggestTimeInput",
       "description": "Suggests time periods across one or more calendars. To access the primary calendar, add 'primary' in the attendee_emails field.\n\nUse this tool for queries like:\n\n * When are all of us free for a meeting?\n * Find a 30 minute slot where we are both available.\n * Check if jane.doe@google.com is free on Monday morning.\n\nExample:\n\n    suggest_time(\n        attendeeEmails=['joedoe@gmail.com', 'janedoe@gmail.com'],\n        startTime='2024-09-10T00:00:00',\n        endTime='2024-09-17T00:00:00',\n        durationMinutes=60,\n        preferences={\n            'startHour': '09:00',\n            'endHour': '17:00',\n            'excludeWeekends': True\n        }\n    )\n    # Returns up to 5 suggested time slots where both users are available for at least one hour between 9:00 AM and 5:00 PM on weekdays from September 10 through September 16, 2024.\n"
     },
     {
       "name": "create_event",
       "input_class_name": "rustic_ai.mcp.connectors.google-calendar.CreateEventInput",
       "description": "Creates a calendar event.\n\nUse this tool for queries like:\n\n * Create an event on my calendar for tomorrow at 2pm called 'Meeting with Jane'.\n * Schedule a meeting with john.doe@google.com next Monday from 10am to 11am.\n\nExample:\n\n    create_event(\n        summary='Meeting with Jane',\n        startTime='2024-09-17T14:00:00',\n        endTime='2024-09-17T15:00:00'\n    )\n    # Creates an event on the primary calendar for September 17, 2024 from 2pm to 3pm called 'Meeting with Jane'.\n"
     },
     {
       "name": "update_event",
       "input_class_name": "rustic_ai.mcp.connectors.google-calendar.UpdateEventInput",
       "description": "Updates a calendar event.\n\nUse this tool for queries like:\n\n * Update the event 'Meeting with Jane' to be one hour later.\n * Add john.doe@google.com to the meeting tomorrow.\n\nExample:\n\n    update_event(\n        eventId='event123',\n        summary='Meeting with Jane and John'\n    )\n    # Updates the summary of event with id 'event123' on the primary calendar to 'Meeting with Jane and John'.\n"
     },
     {
       "name": "delete_event",
       "input_class_name": "rustic_ai.mcp.connectors.google-calendar.DeleteEventInput",
       "description": "Deletes a calendar event.\n\nUse this tool for queries like:\n\n * Delete the event with id event123 on my calendar.\n\nTo cancel or decline an event, use the respond_to_event tool instead.\n\nExample:\n\n    delete_event(\n        eventId='event123'\n    )\n    # Deletes the event with id 'event123' on the user's primary calendar.\n"
     },
     {
       "name": "respond_to_event",
       "input_class_name": "rustic_ai.mcp.connectors.google-calendar.RespondToEventInput",
       "description": "Responds to an event.\n\nUse this tool for queries like:\n\n * Accept the event with id event123 on my calendar.\n * Decline the meeting with Jane.\n * Cancel my next meeting.\n * Tentatively accept the planing meeting.\n\nExample:\n\n    respond_to_event(\n        eventId='event123',\n        responseStatus='accepted'\n    )\n    # Responds with status 'accepted' to the event with id 'event123' on the user's primary calendar.\n"
     }
   ]
 }

"""  # noqa

from enum import Enum
from typing import Annotated, Any, Optional

from pydantic import BaseModel, Field, RootModel


class EventTypeEnum(Enum):
    EVENT_TYPE_UNSPECIFIED = "EVENT_TYPE_UNSPECIFIED"
    DEFAULT = "DEFAULT"
    OUT_OF_OFFICE = "OUT_OF_OFFICE"
    FOCUS_TIME = "FOCUS_TIME"
    WORKING_LOCATION = "WORKING_LOCATION"
    BIRTHDAY = "BIRTHDAY"
    FROM_GMAIL = "FROM_GMAIL"


class ListEventsInput(BaseModel):
    calendarId: Annotated[
        Optional[str],
        Field(description="Optional. The calendar ID to list events from. The default is the user's primary calendar."),
    ] = None
    endTime: Annotated[
        Optional[str],
        Field(
            description=(
                "Optional. Upper bound (exclusive) for the time window to search. Defaults to the end of time. Must be"
                " an ISO 8601 timestamp strictly greater than start_time. For example, 2026-06-03T10:00:00-07:00,"
                " 2026-06-03T10:00:00Z, or 2026-06-03T10:00:00. Milliseconds may be provided but are ignored."
            )
        ),
    ] = None
    eventType: Annotated[
        Optional[list[EventTypeEnum]],
        Field(
            description=(
                "Optional. The event types to return. Possible values are: If empty, only the following event types are"
                " returned: `DEFAULT`, `OUT_OF_OFFICE`, `FOCUS_TIME`, `FROM_GMAIL`"
            )
        ),
    ] = None
    eventTypeFilter: Annotated[
        Optional[list[str]],
        Field(
            deprecated=True,
            description=(
                "Optional. Deprecated: use eventType instead. The event types to return. Possible values are: *"
                " `default` - Regular events (default). * `outOfOffice` - Out of office events. * `focusTime` - Focus"
                " time events. * `workingLocation` - Working location events. * `birthday` - Birthday events. *"
                " `fromGmail` - Events from Gmail. If empty, only the following event types are returned: `default`,"
                " `outOfOffice`, `focusTime`, `fromGmail`"
            ),
        ),
    ] = None
    fullText: Annotated[
        Optional[str],
        Field(
            description=(
                "Optional. Free-form search query to search across title, description, location and attendees. The"
                " search is case-insensitive and supports substring matching. It matches events containing all"
                " individual terms in the query (AND search), regardless of order. Exact phrase matching is not"
                " supported."
            )
        ),
    ] = None
    orderBy: Annotated[
        Optional[str],
        Field(
            description=(
                "Optional. The order in which events should be returned. Possible values are: * `default` -"
                " Unspecified, but deterministic ordering (default). * `startTime` - Order by start time ascending. *"
                " `startTimeDesc` - Order by start time descending. * `lastModified` - Order by last modification time"
                " ascending."
            )
        ),
    ] = None
    pageSize: Annotated[
        Optional[int],
        Field(
            description=(
                "Optional. Maximum number of events returned on one result page. The number of events in the resulting"
                " page may be less than this value, or none at all, even if there are more events matching the query."
                " Incomplete pages can be detected by a non-empty `nextPageToken` field in the response. By default the"
                " value is 100 events. If set, the page size must be positive and not larger than 250 events. It is"
                " recommended to set pageSize=10 for most queries to save context and use `nextPageToken` to fetch"
                " additional pages."
            )
        ),
    ] = None
    pageToken: Annotated[
        Optional[str], Field(description="Optional. A token retrieved from a previous response's nextPageToken field.")
    ] = None
    startTime: Annotated[
        Optional[str],
        Field(
            description=(
                "Optional. Lower bound (exclusive) for the time window to search. Defaults to the current time if"
                " neither time bound is provided, or the beginning of time if only end_time is provided. Must be an ISO"
                " 8601 timestamp strictly less than end_time. Milliseconds may be provided but are ignored."
            )
        ),
    ] = None
    timeZone: Annotated[
        Optional[str],
        Field(
            description=(
                "Optional. Time zone used in the response and to resolve timezone-less dates in the request (formatted"
                " as an IANA Time Zone Database name, e.g. `Europe/Zurich`). The default is the time zone of the"
                " calendar."
            )
        ),
    ] = None


class GetEventInput(BaseModel):
    calendarId: Annotated[
        Optional[str],
        Field(
            description="Optional. The calendar ID to get the event from. The default is the user's primary calendar."
        ),
    ] = None
    eventId: Annotated[str, Field(description="Required. The ID of the event to get.")]


class ListCalendarsInput(BaseModel):
    pageSize: Annotated[
        Optional[int],
        Field(
            description=(
                "Optional. Maximum number of entries returned on one result page. By default the value is 100 entries."
                " The page size can never be larger than 250 entries."
            )
        ),
    ] = None
    pageToken: Annotated[
        Optional[str], Field(description="Optional. Token specifying which result page to return.")
    ] = None


class Availability(Enum):
    """
    Optional. Whether the event blocks time on the calendar.
    """

    AVAILABILITY_UNSPECIFIED = "AVAILABILITY_UNSPECIFIED"
    AVAILABILITY_BUSY = "AVAILABILITY_BUSY"
    AVAILABILITY_FREE = "AVAILABILITY_FREE"


class EventType(Enum):
    """
    Optional. Type of the event. Possible values for creation are: * `DEFAULT` - Default event type. *
    `OUT_OF_OFFICE` - Out of office event type. * `FOCUS_TIME` - Focus time event type. * `WORKING_LOCATION` -
    Working location event type. * `BIRTHDAY` - Birthday event type.
    """

    EVENT_TYPE_UNSPECIFIED = "EVENT_TYPE_UNSPECIFIED"
    DEFAULT = "DEFAULT"
    OUT_OF_OFFICE = "OUT_OF_OFFICE"
    FOCUS_TIME = "FOCUS_TIME"
    WORKING_LOCATION = "WORKING_LOCATION"
    BIRTHDAY = "BIRTHDAY"
    FROM_GMAIL = "FROM_GMAIL"


class NotificationLevel(Enum):
    """
    Optional. Which email notification should be sent for this event update. Possible values are: * `NONE` - No email
    notifications are sent. * `EXTERNAL_ONLY` - Only external (non-Calendar) attendees receive email notifications (
    default). * `ALL` - All event attendees receive email notifications.
    """

    NOTIFICATION_LEVEL_UNSPECIFIED = "NOTIFICATION_LEVEL_UNSPECIFIED"
    NONE = "NONE"
    EXTERNAL_ONLY = "EXTERNAL_ONLY"
    ALL = "ALL"


class DeleteEventInput(BaseModel):
    """
    Request message for DeleteEvent.
    """

    calendarId: Annotated[
        Optional[str],
        Field(
            description="Optional. The calendar ID of the event to delete. The default is the user's primary calendar."
        ),
    ] = None
    eventId: Annotated[str, Field(description="Required. The ID of the event to delete.")]
    notificationLevel: Annotated[
        Optional[NotificationLevel],
        Field(
            description=(
                "Optional. Which email notification should be sent for this event update. Possible values are: * `NONE`"
                " - No email notifications are sent. * `EXTERNAL_ONLY` - Only external (non-Calendar) attendees receive"
                " email notifications (default). * `ALL` - All event attendees receive email notifications."
            )
        ),
    ] = None


class RespondToEventInput(BaseModel):
    """
    Request message for RespondToEvent.
    """

    calendarId: Annotated[
        Optional[str],
        Field(
            description=(
                "Optional. The calendar ID of the event to respond to. The default is the user's primary calendar."
            )
        ),
    ] = None
    eventId: Annotated[str, Field(description="Required. The ID of the event to respond to.")]
    notificationLevel: Annotated[
        Optional[NotificationLevel],
        Field(
            description=(
                "Optional. Which email notification should be sent for this event update. Possible values are: * `NONE`"
                " - No email notifications are sent. * `EXTERNAL_ONLY` - Only external (non-Calendar) attendees receive"
                " email notifications (default). * `ALL` - All event attendees receive email notifications."
            )
        ),
    ] = None
    responseComment: Annotated[
        Optional[str], Field(description="Optional. The user's comment attached to the response.")
    ] = None
    responseStatus: Annotated[
        str,
        Field(
            description=(
                "Required. The new user's response status of the event. Possible values are: * `declined` - The"
                " attendee has declined the invitation. * `tentative` - The attendee has tentatively accepted the"
                " invitation. * `accepted` - The attendee has accepted the invitation."
            )
        ),
    ]


class Attachment(RootModel[Any]):
    root: Any


class Attendee(RootModel[Any]):
    root: Any


class GuestPermissions(RootModel[Any]):
    root: Any


class Preferences(RootModel[Any]):
    root: Any


class Reminder(RootModel[Any]):
    root: Any


class WorkingLocationProperties(RootModel[Any]):
    root: Any


class SuggestTimeInput(BaseModel):
    """
    Request message for SuggestTime.
    """

    attendeeEmails: Annotated[list[str], Field(description="Required. The attendee emails to find free time for.")]
    durationMinutes: Annotated[
        Optional[int],
        Field(description="Optional. Minimum duration of a free time slot in minutes. The default is 30 minutes."),
    ] = None
    endTime: Annotated[
        str, Field(description="Required. The end of the interval for the query formatted as per ISO 8601.")
    ]
    preferences: Annotated[Optional[Preferences], Field(description="The preferences to find suggested time for.")] = (
        None
    )
    startTime: Annotated[
        str, Field(description="Required. The start of the interval for the query formatted as per ISO 8601.")
    ]
    timeZone: Annotated[
        Optional[str],
        Field(
            description=(
                "Optional. Time zone used for the time values. This field accepts IANA Time Zone database names, e.g.,"
                " `America/Los_Angeles`. The default is the time zone of the user's primary calendar."
            )
        ),
    ] = None


class CreateEventInput(BaseModel):
    """
    Request message for CreateEvent.
    """

    addGoogleMeetUrl: Annotated[
        Optional[bool],
        Field(
            description=(
                "Optional. Whether to create and attach a video conference URL for the event. Defaults to False."
            )
        ),
    ] = None
    allDay: Annotated[
        Optional[bool],
        Field(
            description=(
                "Optional. Whether the event is an all-day event. The default is False. If true, the start and end time"
                " are treated as midnight."
            )
        ),
    ] = None
    attachments: Annotated[
        Optional[list[Attachment]], Field(description="Optional. File attachments for the event.")
    ] = None
    attendeeEmails: Annotated[
        Optional[list[str]],
        Field(
            deprecated=True,
            description=(
                "Optional. Deprecated: use `attendees` instead. The additional attendees of the event, as email"
                " addresses. For events that are created on the user's primary calendar with at least one other"
                " attendee, the current user will automatically be added as an attendee if not already included in this"
                " list."
            ),
        ),
    ] = None
    attendees: Annotated[
        Optional[list[Attendee]],
        Field(
            description=(
                "Optional. The additional attendees of the event. For events that are created on the user's primary"
                " calendar with at least one other attendee, the current user will automatically be added as an"
                " attendee if not already included in this list."
            )
        ),
    ] = None
    availability: Annotated[
        Optional[Availability], Field(description="Optional. Whether the event blocks time on the calendar.")
    ] = None
    calendarId: Annotated[
        Optional[str],
        Field(
            description="Optional. The calendar ID to create the event on. The default is the user's primary calendar."
        ),
    ] = None
    colorId: Annotated[
        Optional[str],
        Field(
            description=(
                "Optional. The color of the event. This is an ID referring to an entry in the calendar's color palette."
                " Event color ID (string `1`-`11`): * 1: Lavender * 2: Sage * 3: Grape * 4: Flamingo * 5: Banana * 6:"
                " Tangerine * 7: Peacock * 8: Graphite * 9: Blueberry * 10: Basil * 11: Tomato."
            )
        ),
    ] = None
    description: Annotated[
        Optional[str], Field(description="Optional. Description of the event. Can contain HTML.")
    ] = None
    endTime: Annotated[
        str,
        Field(
            description=(
                "Required. The end time of the event. Must be a full ISO 8601 timestamp (e.g., '2026-04-30T10:00:00Z')."
            )
        ),
    ]
    eventType: Annotated[
        Optional[EventType],
        Field(
            description=(
                "Optional. Type of the event. Possible values for creation are: * `DEFAULT` - Default event type. *"
                " `OUT_OF_OFFICE` - Out of office event type. * `FOCUS_TIME` - Focus time event type. *"
                " `WORKING_LOCATION` - Working location event type. * `BIRTHDAY` - Birthday event type."
            )
        ),
    ] = None
    googleMeetUrl: Annotated[
        Optional[str],
        Field(
            description=(
                "Optional. Allows attaching an existing Google Meet URL or meeting ID to the event. If set, this URL"
                " will be attached to the event instead of generating a new Google Meet room, even if"
                " `addGoogleMeetUrl` is set to `true`."
            )
        ),
    ] = None
    guestPermissions: Annotated[
        Optional[GuestPermissions], Field(description="Optional. Guest permissions settings for this event.")
    ] = None
    location: Annotated[
        Optional[str], Field(description="Optional. Geographic location of the event as free-form text.")
    ] = None
    notificationLevel: Annotated[
        Optional[NotificationLevel],
        Field(
            description=(
                "Optional. Which email notification should be sent for this event update. Possible values are: * `NONE`"
                " - No email notifications are sent. * `EXTERNAL_ONLY` - Only external (non-Calendar) attendees receive"
                " email notifications (default). * `ALL` - All event attendees receive email notifications."
            )
        ),
    ] = None
    overrideReminders: Annotated[
        Optional[list[Reminder]],
        Field(
            description=(
                "Optional. Reminders defined for this event, overriding the default reminders for the calendar. If not"
                " set, the event will use the default reminders of the calendar."
            )
        ),
    ] = None
    recurrenceData: Annotated[
        Optional[list[str]],
        Field(
            description=(
                "Optional. The recurrence data of the event as RRULE, RDATE, or EXDATE strings per RFC 5545. Each"
                " string in the list acts as a separate RFC 5545 line. The API normalizes recurrence strings upon"
                " creation (e.g., converting absolute UTC EXDATEs into formulations bound to the event's assigned time"
                " zone)."
            )
        ),
    ] = None
    startTime: Annotated[str, Field(description="Required. The start time of the event formatted as per ISO 8601.")]
    summary: Annotated[str, Field(description="Required. Title of the event.")]
    timeZone: Annotated[
        Optional[str],
        Field(
            description=(
                "Optional. Time zone of the event formatted as a strictly case-sensitive IANA Time Zone Database name"
                " (e.g., 'America/Los_Angeles'). Defaults to the user's primary time zone if omitted. Dictates the"
                " display time zone, overriding timezone offsets provided in start_time or end_time (e.g."
                " 'Europe/Zurich')."
            )
        ),
    ] = None
    visibility: Annotated[
        Optional[str],
        Field(
            description=(
                "Optional. Visibility of the event. Possible values are: * `default` - Uses the default visibility for"
                " events on the calendar. This is the default value. * `public` - The event is public and event details"
                " are visible to all readers of the calendar. * `private` - The event is private and only event"
                " attendees may view event details."
            )
        ),
    ] = None
    workingLocationProperties: Annotated[
        Optional[WorkingLocationProperties],
        Field(
            description=(
                "Optional. Properties for working location events. Used only when `eventType` is `WORKING_LOCATION`."
            )
        ),
    ] = None


class UpdateEventInput(BaseModel):
    """
    Request message for UpdateEvent.
    """

    addGoogleMeetUrl: Annotated[
        Optional[bool],
        Field(
            description=(
                "Optional. Allows to create or update a Google Meet url for the event. By default, no Google Meet url"
                " is created or updated. No Google Meet url is created or updated if Meet is disabled for the user, but"
                " the event update will succeed."
            )
        ),
    ] = None
    addedAttachments: Annotated[
        Optional[list[Attachment]], Field(description="Optional. File attachments to add to the event.")
    ] = None
    addedAttendeeEmails: Annotated[
        Optional[list[str]],
        Field(
            deprecated=True,
            description=(
                "Optional. Deprecated: use `added_attendees` instead. The additional attendees of the event, as email"
                " addresses."
            ),
        ),
    ] = None
    addedAttendees: Annotated[
        Optional[list[Attendee]],
        Field(
            description=(
                "Optional. The additional attendees of the event. Updates the attendees of the event if the attendee is"
                " not already present."
            )
        ),
    ] = None
    allDay: Annotated[
        Optional[bool],
        Field(
            description=(
                "Optional. Whether the event is an all-day event. Will not be updated if not set. This field can be"
                " used to update a timed event to an all-day event and vice versa. If set, `start_time` and `end_time`"
                " must also be provided. If true, the start and end time are treated as midnight."
            )
        ),
    ] = None
    availability: Annotated[
        Optional[Availability], Field(description="Optional. Whether the event blocks time on the calendar.")
    ] = None
    calendarId: Annotated[
        Optional[str],
        Field(
            description="Optional. The calendar ID of the event to update. The default is the user's primary calendar."
        ),
    ] = None
    colorId: Annotated[
        Optional[str],
        Field(
            description=(
                "Optional. New color ID of the event. Will not be updated if not set. Event color ID (string `1`-`11`):"
                " * 1: Lavender * 2: Sage * 3: Grape * 4: Flamingo * 5: Banana * 6: Tangerine * 7: Peacock * 8:"
                " Graphite * 9: Blueberry * 10: Basil * 11: Tomato."
            )
        ),
    ] = None
    description: Annotated[
        Optional[str], Field(description="Optional. The new description of the event. Will not be updated if not set.")
    ] = None
    endTime: Annotated[
        Optional[str],
        Field(
            description=(
                "Optional. The new end time of the event formatted as per ISO 8601. Will not be updated if not set."
            )
        ),
    ] = None
    eventId: Annotated[str, Field(description="Required. The ID of the event to update.")]
    googleMeetUrl: Annotated[
        Optional[str],
        Field(
            description=(
                "Optional. Allows attaching an existing Google Meet URL or meeting ID to the event. If set, this URL"
                " will be attached to the event instead of generating a new Google Meet room, even if"
                " `addGoogleMeetUrl` is set to `true`."
            )
        ),
    ] = None
    guestPermissions: Annotated[
        Optional[GuestPermissions], Field(description="Optional. Guest permissions settings for this event.")
    ] = None
    location: Annotated[
        Optional[str], Field(description="Optional. The new location of the event. Will not be updated if not set.")
    ] = None
    notificationLevel: Annotated[
        Optional[NotificationLevel],
        Field(
            description=(
                "Optional. Which email notification should be sent for this event update. Possible values are: * `NONE`"
                " - No email notifications are sent. * `EXTERNAL_ONLY` - Only external (non-Calendar) attendees receive"
                " email notifications (default). * `ALL` - All event attendees receive email notifications."
            )
        ),
    ] = None
    overrideReminders: Annotated[
        Optional[list[Reminder]],
        Field(
            description=(
                "Optional. Reminders defined for this event, overriding any existing reminders and the default"
                " reminders for the calendar. If set, this will replace all existing reminders on the event. If not"
                " set, reminders will not be updated."
            )
        ),
    ] = None
    removedAttachmentFileUrls: Annotated[
        Optional[list[str]], Field(description="Optional. File attachments to remove from the event.")
    ] = None
    removedAttendeeEmails: Annotated[
        Optional[list[str]], Field(description="Optional. The attendees of the event to remove, as email addresses.")
    ] = None
    startTime: Annotated[
        Optional[str],
        Field(
            description=(
                "Optional. The new start time of the event formatted as per ISO 8601. Will not be updated if not set."
            )
        ),
    ] = None
    summary: Annotated[
        Optional[str], Field(description="Optional. The new title of the event. Will not be updated if not set.")
    ] = None
    timeZone: Annotated[
        Optional[str],
        Field(
            description=(
                "Optional. Time zone of the event formatted as a strictly case-sensitive IANA Time Zone Database name"
                " (e.g., 'America/Los_Angeles'). Defaults to the user's primary time zone if omitted and the event's"
                " start or end times are updated. Dictates the display time zone, overriding timezone offsets provided"
                " in start_time or end_time (e.g. 'Europe/Zurich')."
            )
        ),
    ] = None
    visibility: Annotated[
        Optional[str],
        Field(
            description=(
                "Optional. New visibility of the event. Possible values are: * `default` - Uses the default visibility"
                " for events on the calendar. This is the default value. * `public` - The event is public and event"
                " details are visible to all readers of the calendar. * `private` - The event is private and only event"
                " attendees may view event details."
            )
        ),
    ] = None
