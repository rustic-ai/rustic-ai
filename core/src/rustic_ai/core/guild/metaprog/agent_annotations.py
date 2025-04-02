from enum import StrEnum


class AgentAnnotations(StrEnum):
    """
    Enum class to represent the annotations for the agent.
    """

    ISHANDLER = "__rustic_handler__"
    HANDLES_RAW = "__rustic_handles_raw__"
    MESSAGE_FORMAT = "__rustic_handler_message_format__"
    HANDLE_ESSENTIAL = "__rustic__handle_essential__"
    DEPENDS_ON = "__rustic__depends_on__"

    IS_BEFORE_PROCESS_FIXTURE = "__rustic__is_before_fixture__"
    IS_AFTER_PROCESS_FIXTURE = "__rustic__is_after_fixture__"
    IS_ON_SEND_FIXTURE = "__rustic__is_on_send_fixture__"
    IS_ON_SEND_ERROR_FIXTURE = "__rustic__is_on_error_fixture__"
    IS_MESSAGE_MOD_FIXTURE = "__rustic__is_message_mod_fixture__"
