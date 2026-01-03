import json
import time

import pytest

from rustic_ai.core.messaging.core.message import (
    AgentTag,
    ForwardHeader,
    FunctionalTransformer,
    Message,
    MessageConstants,
    MessageRoutable,
    PayloadTransformer,
)
from rustic_ai.core.utils import jx
from rustic_ai.core.utils.gemstone_id import GemstoneGenerator
from rustic_ai.core.utils.jexpr import JExpr, JFn, JObj, JxScript
from rustic_ai.core.utils.priority import Priority


@pytest.fixture
def generator():
    """
    Fixture that returns a GemstoneGenerator instance with a seed of 1.
    """
    return GemstoneGenerator(1)


class TestMessage:
    """
    A class that contains unit tests for the Message class.
    """

    def test_create_message_with_default_parameters(self, generator):
        """
        Tests that a Message object can be created with default parameters and all attributes are set correctly.
        """
        msg_id = generator.get_id(Priority.NORMAL)
        message = Message(
            topics="topic",
            sender=AgentTag(id="senderId", name="sender"),
            payload={"key": "value"},
            id_obj=msg_id,
        )
        assert message.topics == "topic"
        assert message.sender.id == "senderId"
        assert message.sender.name == "sender"
        assert message.payload == {"key": "value"}
        assert message.priority == Priority.NORMAL
        assert message.in_response_to is None
        assert message.current_thread_id == msg_id.to_int()
        assert message.recipient_list == []
        assert isinstance(message.id, int)
        assert message.format == MessageConstants.RAW_JSON_FORMAT

    def test_compare_messages_with_different_ids(self, generator):
        """
        Tests that the __lt__ method returns the expected result when comparing two Message objects with different IDs.
        """
        message1 = Message(
            topics="topic",
            sender=AgentTag(id="senderId", name="sender"),
            payload={"key": "value"},
            format=MessageConstants.RAW_JSON_FORMAT,
            id_obj=generator.get_id(Priority.NORMAL),
        )
        message2 = Message(
            topics="topic",
            sender=AgentTag(id="senderId", name="sender"),
            payload={"key": "value"},
            format=MessageConstants.RAW_JSON_FORMAT,
            id_obj=generator.get_id(Priority.NORMAL),
        )
        assert message1 < message2

    def test_compare_messages_with_same_id(self, generator):
        """
        Tests that the __eq__ method returns the expected result when comparing two Message objects with the same ID.
        """
        id = generator.get_id(Priority.NORMAL)
        message1 = Message(
            topics="topic",
            sender=AgentTag(id="senderId", name="sender"),
            payload={"key": "value"},
            format=MessageConstants.RAW_JSON_FORMAT,
            id_obj=id,
        )
        message2 = Message(
            topics="topic",
            sender=AgentTag(id="senderId", name="sender"),
            payload={"key": "value"},
            format=MessageConstants.RAW_JSON_FORMAT,
            id_obj=id,
        )
        assert message1 == message2

    def test_create_message_with_empty_topic(self, generator):
        """
        Tests that a ValueError is raised when creating a Message object with an empty topic.
        """
        with pytest.raises(ValueError):
            Message(
                topics="",
                sender=AgentTag(id="senderId", name="sender"),
                payload={"key": "value"},
                format=MessageConstants.RAW_JSON_FORMAT,
                id_obj=generator.get_id(Priority.NORMAL),
            )

    def test_create_message_with_empty_sender(self, generator):
        """
        Tests that a ValueError is raised when creating a Message object with an empty sender.
        """
        with pytest.raises(ValueError):
            Message(
                topics="topic",
                sender="",
                payload={"key": "value"},
                format=MessageConstants.RAW_JSON_FORMAT,
                id_obj=generator.get_id(Priority.NORMAL),
            )

    def test_create_message_with_empty_data(self, generator):
        """
        Tests that a ValueError is raised when creating a Message object with an empty data dictionary.
        """
        with pytest.raises(ValueError):
            Message(
                topics="topic",
                sender=AgentTag(id="senderId", name="sender"),
                payload={},
                format=MessageConstants.RAW_JSON_FORMAT,
                id_obj=generator.get_id(Priority.NORMAL),
            )

    def test_create_message_with_incorrect_data(self, generator):
        """
        Tests that a ValueError is raised when creating a Message object with non-serializable data.
        """
        with pytest.raises(ValueError):
            Message(
                topics="topic",
                sender=AgentTag(id="senderId", name="sender"),
                payload=print,
                format=MessageConstants.RAW_JSON_FORMAT,
                id_obj=generator.get_id(Priority.NORMAL),
            )  # type: ignore

    def test_create_message_with_non_gemstone_id_id(self):
        """
        Tests that a ValueError is raised when creating a Message object with a non-GemstoneID ID.
        """
        with pytest.raises(ValueError):
            Message(
                topics="topic",
                sender=AgentTag(id="senderId", name="sender"),
                payload={"key": "value"},
                format=MessageConstants.RAW_JSON_FORMAT,
                id_obj=123,  # type: ignore
            )

    def test_create_message_with_no_id(self):
        """
        Tests that a ValueError is raised when creating a Message object with no ID.
        """
        with pytest.raises(ValueError):
            Message(
                topics="topic",
                sender=AgentTag(id="senderId", name="sender"),
                payload={"key": "value"},
                format=MessageConstants.RAW_JSON_FORMAT,
                id_obj=None,  # type: ignore
            )

    def test_create_message_with_extra_parameters(self, generator):
        """
        Tests that a ValueError is raised when creating a Message object with extra parameters.
        """
        with pytest.raises(ValueError):
            Message(
                topics="topic",
                sender=AgentTag(id="senderId", name="sender"),
                payload={"key": "value"},
                format=MessageConstants.RAW_JSON_FORMAT,
                id_obj=generator.get_id(Priority.NORMAL),
                extra_parameter="extra",
            )

    def test_create_message_with_internal_id(self, generator):
        """
        Tests that a ValueError is raised when creating a Message object with _id.
        """
        with pytest.raises(ValueError):
            Message(
                topics="topic",
                sender=AgentTag(id="senderId", name="sender"),
                payload={"key": "value"},
                format=MessageConstants.RAW_JSON_FORMAT,
                id_obj=generator.get_id(Priority.NORMAL),
                _id=123,
            )

    def test_message_encoder_encodes_message_to_json(self, generator):
        """
        Tests that MessageEncoder encodes a Message object to JSON.
        """
        msg_id = generator.get_id(Priority.NORMAL)
        message = Message(
            topics="topic",
            sender=AgentTag(id="senderId", name="sender"),
            payload={"key": "value"},
            format=MessageConstants.RAW_JSON_FORMAT,
            id_obj=msg_id,
            recipient_list=[AgentTag(id="taggedAgentId", name="taggedAgent")],
        )
        json_message = message.to_json()
        assert isinstance(json_message, str)

        expected_json_message = json.loads(
            '{"topics":"topic","sender":{"id":"senderId","name":"sender"},"format":"generic_json",'
            + '"payload":{"key":"value"},"in_response_to":null,'
            + '"recipient_list":[{"id":"taggedAgentId","name":"taggedAgent"}],'
            + f'"thread":[{msg_id.to_int()}], "forward_header": null,'
            + '"conversation_id":null, "routing_slip":null,'
            + '"message_history":[],"ttl":null, "traceparent": null, "id":'
            + str(message.id)
            + ',"priority":4,"is_error_message": false, "timestamp":'
            + str(msg_id.timestamp)
            + ', "session_state": null, "topic_published_to": null, "enrich_with_history": 0'
            + ',"process_status": null, "origin_guild_stack": []}'
        )
        assert json.loads(json_message) == expected_json_message

    def test_message_decoder_decodes_json_to_message(self, generator):
        """
        Tests that MessageDecoder decodes a JSON string to a Message object.
        """
        id = generator.get_id(Priority.LOW)
        id_reply = generator.get_id(Priority.NORMAL)
        id_thread = generator.get_id(Priority.NORMAL)

        json_message = (
            '{"id": '
            + str(id.to_int())
            + ', "topics": "topic", "sender": {"id":"senderId", "name":"sender"}, "format":"generic_json" '
            + ',"payload": {"key": "value"}, "priority": 5, "in_response_to": '
            + str(id_reply.to_int())
            + ', "thread": '
            + str([id_thread.to_int()])
            + ', "recipient_list": [], "forward_header": null}'
        )

        message = Message.from_json(json_message)
        assert isinstance(message, Message)
        assert message.id == id.to_int()
        assert message.topics == "topic"
        assert message.sender.id == "senderId"
        assert message.sender.name == "sender"
        assert message.payload == {"key": "value"}
        assert message.priority == Priority.LOW
        assert message.in_response_to == id_reply.to_int()
        assert message.current_thread_id == id_thread.to_int()
        assert message.recipient_list == []
        assert message.forward_header is None

    def test_message_decoder_decodes_json_to_message_with_no_id(self):
        """
        Tests that a ValueError is raised when decoding a JSON string with no ID.
        """
        with pytest.raises(ValueError):
            Message.from_json(
                '{"topic": "topic", "sender": "sender", "format":"generic_json", "payload": {"key": "value"}, '
                + '"priority": 5, "in_response_to": null, "recipient_list": []}'
            )

    def test_json_conversion(self, generator):
        gemstone_id = generator.get_id(Priority.NORMAL)
        origin_gemstone_id = generator.get_id(Priority.NORMAL)
        message = Message(
            gemstone_id,
            topics="topic1",
            sender=AgentTag(id="senderId", name="sender"),
            format=MessageConstants.RAW_JSON_FORMAT,
            payload={"key": "value"},
            recipient_list=[AgentTag(id="taggedAgentId", name="taggedAgent")],
            forward_header=ForwardHeader(
                origin_message_id=origin_gemstone_id.to_int(),
                on_behalf_of=AgentTag(id="onBehalfOfId", name="onBehalfOf"),
            ),
        )
        json_str = message.to_json()
        new_message = Message.from_json(json_str)
        assert message == new_message

    def test_message_decoder_without_id(self, generator):
        """
        Tests that a ValueError is raised when decoding a JSON string without an ID.
        """
        with pytest.raises(ValueError):
            Message.from_json(
                '{"topic": "topic", "sender": "sender", "data_type"="generic_json", "payload": {"key": "value"}}'
            )

    def test_message_ordering_by_priority(self, generator):
        """
        Tests that Message objects are ordered by priority.
        """
        id1 = generator.get_id(Priority.NORMAL)
        id2 = generator.get_id(Priority.HIGH)
        time.sleep(0.001)
        id3 = generator.get_id(Priority.LOW)
        id4 = generator.get_id(Priority.NORMAL)
        id5 = generator.get_id(Priority.URGENT)
        id6 = generator.get_id(Priority.LOW)

        sender = AgentTag(id="senderId", name="sender")

        m1 = Message(
            topics="topic",
            sender=sender,
            payload={"key": "value"},
            format=MessageConstants.RAW_JSON_FORMAT,
            id_obj=id1,
        )
        m2 = Message(
            topics="topic",
            sender=sender,
            payload={"key": "value"},
            format=MessageConstants.RAW_JSON_FORMAT,
            id_obj=id2,
        )
        m3 = Message(
            topics="topic",
            sender=sender,
            payload={"key": "value"},
            format=MessageConstants.RAW_JSON_FORMAT,
            id_obj=id3,
        )
        m4 = Message(
            topics="topic",
            sender=sender,
            payload={"key": "value"},
            format=MessageConstants.RAW_JSON_FORMAT,
            id_obj=id4,
        )
        m5 = Message(
            topics="topic",
            sender=sender,
            payload={"key": "value"},
            format=MessageConstants.RAW_JSON_FORMAT,
            id_obj=id5,
        )
        m6 = Message(
            topics="topic",
            sender=sender,
            payload={"key": "value"},
            format=MessageConstants.RAW_JSON_FORMAT,
            id_obj=id6,
        )

        sorted_ids = sorted([m1, m2, m3, m4, m5, m6])
        assert sorted_ids == [m5, m2, m1, m4, m3, m6]

    def test_simple_transformer(self, generator):
        transformer = PayloadTransformer(expression="$")

        origin = Message(
            id_obj=generator.get_id(Priority.NORMAL),
            topics="default_topic",
            sender=AgentTag(id="senderId", name="sender"),
            payload={"origin_key": "origin_value"},
            format=MessageConstants.RAW_JSON_FORMAT,
        )

        routable = MessageRoutable(
            topics="default_topic",
            priority=Priority.NORMAL,
            recipient_list=[],
            payload={"key": "value"},
            format=MessageConstants.RAW_JSON_FORMAT,
            forward_header=None,
        )

        transformed = transformer.transform(origin=origin, agent_state={}, guild_state={}, routable=routable)

        assert transformed is not None
        assert transformed.payload == {"key": "value"}

    def test_simple_transformer_with_expression(self, generator):
        transformer = PayloadTransformer(expression="{'new_key': $.key}")
        origin = Message(
            id_obj=generator.get_id(Priority.NORMAL),
            topics="default_topic",
            sender=AgentTag(id="senderId", name="sender"),
            payload={"origin_key": "origin_value"},
            format=MessageConstants.RAW_JSON_FORMAT,
        )

        routable = MessageRoutable(
            topics="default_topic",
            priority=Priority.NORMAL,
            recipient_list=[],
            payload={"key": "value"},
            format=MessageConstants.RAW_JSON_FORMAT,
            forward_header=None,
        )

        transformed = transformer.transform(origin=origin, agent_state={}, guild_state={}, routable=routable)

        assert transformed is not None
        assert transformed.payload == {"new_key": "value"}

    def test_simple_transformer_with_invalid_expression(self, generator):
        transformer = PayloadTransformer(expression="$.key")
        origin = Message(
            id_obj=generator.get_id(Priority.NORMAL),
            topics="default_topic",
            sender=AgentTag(id="senderId", name="sender"),
            payload={"origin_key": "origin_value"},
            format=MessageConstants.RAW_JSON_FORMAT,
        )

        routable = MessageRoutable(
            topics="default_topic",
            priority=Priority.NORMAL,
            recipient_list=[],
            payload={"key2": "value"},
            format=MessageConstants.RAW_JSON_FORMAT,
            forward_header=None,
        )

        transformed = transformer.transform(origin=origin, agent_state={}, guild_state={}, routable=routable)

        assert transformed is None

    def test_functional_transformer(self, generator):

        handler = JxScript(
            JObj(
                {
                    "output_format": "generic_json",
                    "payload": JObj(
                        {
                            "new_key": JExpr("payload").key,
                            "origin_id": JExpr("$").origin.id,
                        }
                    ),
                }
            )
        ).serialize()

        transformer = FunctionalTransformer(handler=handler)

        origin = Message(
            id_obj=generator.get_id(Priority.NORMAL),
            topics="default_topic",
            sender=AgentTag(id="senderId", name="sender"),
            payload={"origin_key": "origin_value"},
            format=MessageConstants.RAW_JSON_FORMAT,
        )

        routable = MessageRoutable(
            topics="default_topic",
            priority=Priority.NORMAL,
            recipient_list=[],
            payload={"key": "value"},
            format=MessageConstants.RAW_JSON_FORMAT,
            forward_header=None,
        )

        transformed = transformer.transform(origin=origin, agent_state={}, guild_state={}, routable=routable)

        assert transformed is not None
        assert transformed.payload == {"new_key": "value", "origin_id": origin.id}

    def test_functional_conditional_transformer(self, generator):

        handler = JxScript(
            JObj(
                {
                    "output_format": MessageConstants.RAW_JSON_FORMAT,
                    "payload": JObj(
                        {
                            "new_key": JExpr("payload").key,
                            "big_small": jx.ternary(JExpr("payload").numkey > 10, "big", "small"),
                            "origin_id": JExpr("$").origin.id,
                        }
                    ),
                }
            )
        ).serialize()

        transformer = FunctionalTransformer(handler=handler)

        origin = Message(
            id_obj=generator.get_id(Priority.NORMAL),
            topics="default_topic",
            sender=AgentTag(id="senderId", name="sender"),
            payload={"origin_key": "origin_value"},
            format=MessageConstants.RAW_JSON_FORMAT,
        )

        routable = MessageRoutable(
            topics="default_topic",
            priority=Priority.NORMAL,
            recipient_list=[],
            payload={"key": "value", "numkey": 15},
            format=MessageConstants.RAW_JSON_FORMAT,
            forward_header=None,
        )

        routable2 = MessageRoutable(
            topics="default_topic",
            priority=Priority.NORMAL,
            recipient_list=[],
            payload={"key": "value", "numkey": 5},
            format=MessageConstants.RAW_JSON_FORMAT,
            forward_header=None,
        )

        transformed = transformer.transform(origin=origin, agent_state={}, guild_state={}, routable=routable)

        assert transformed is not None
        assert transformed.payload == {
            "new_key": "value",
            "origin_id": origin.id,
            "big_small": "big",
        }

        transformed = transformer.transform(origin=origin, agent_state={}, guild_state={}, routable=routable2)

        assert transformed is not None
        assert transformed.payload == {
            "new_key": "value",
            "origin_id": origin.id,
            "big_small": "small",
        }

    def test_functional_xform_with_functions(self, generator):

        one_form = jx.assign(
            "$OneForm",
            JFn(
                [],
                JObj(
                    {
                        "topics": "topic_one",
                        "format": "ONE_FORM",
                        "payload": JObj(
                            {
                                "key_one": JExpr("payload").key,
                                "origin_id": JExpr("$").origin.id,
                            }
                        ),
                    }
                ),
            ),
        )

        two_form = jx.assign(
            "$TwoForm",
            JFn(
                [],
                JObj(
                    {
                        "topics": ["topic_two"],
                        "format": "TWO_FORM",
                        "payload": JObj(
                            {
                                "key_two": JExpr("payload").key,
                                "origin_id": JExpr("$").origin.id,
                            }
                        ),
                    }
                ),
            ),
        )

        handler = JxScript(
            one_form,
            two_form,
            jx.ternary(JExpr("payload").numkey > 10, JExpr("$OneForm()"), JExpr("$TwoForm()")),
        ).serialize()

        transformer = FunctionalTransformer(handler=handler)

        origin = Message(
            id_obj=generator.get_id(Priority.NORMAL),
            topics="default_topic",
            sender=AgentTag(id="senderId", name="sender"),
            payload={"origin_key": "origin_value"},
            format=MessageConstants.RAW_JSON_FORMAT,
        )

        routable = MessageRoutable(
            topics="default_topic",
            priority=Priority.NORMAL,
            recipient_list=[],
            payload={"key": "value", "numkey": 15},
            format=MessageConstants.RAW_JSON_FORMAT,
            forward_header=None,
        )

        transformed = transformer.transform(origin=origin, agent_state={}, guild_state={}, routable=routable)

        assert transformed is not None
        assert transformed.payload == {"key_one": "value", "origin_id": origin.id}
        assert transformed.format == "ONE_FORM"
        assert transformed.topics == "topic_one"

        routable2 = MessageRoutable(
            topics="default_topic",
            priority=Priority.NORMAL,
            recipient_list=[],
            payload={"key": "value", "numkey": 5},
            format=MessageConstants.RAW_JSON_FORMAT,
            forward_header=None,
        )

        transformed = transformer.transform(origin=origin, agent_state={}, guild_state={}, routable=routable2)

        assert transformed is not None
        assert transformed.payload == {"key_two": "value", "origin_id": origin.id}
        assert transformed.format == "TWO_FORM"
        assert transformed.topics == ["topic_two"]
