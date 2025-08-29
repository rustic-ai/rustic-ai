from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ArrayOfContentParts,
    AssistantMessage,
    ChatCompletionRequest,
    FileContentPart,
    FileUrl,
    ImageContentPart,
    ImageUrl,
    SystemMessage,
    TextContentPart,
    UserMessage,
)
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.core.utils.gemstone_id import GemstoneGenerator
from rustic_ai.llm_agent import LLMAgentUtils


class TestLLMAgentUtils:
    def test_has_attachments(self, generator: GemstoneGenerator, build_message_from_payload):
        message = build_message_from_payload(
            generator,
            ChatCompletionRequest(
                messages=[
                    UserMessage(
                        content=ArrayOfContentParts(
                            root=[
                                FileContentPart(file_url=FileUrl(url="http://example.com/file1")),
                                TextContentPart(text="Hello"),
                            ]
                        )
                    ),
                    AssistantMessage(content="Hi there!"),
                    UserMessage(content="Hello world!"),  # Non-dict content
                ]
            ),
        )
        assert LLMAgentUtils.has_attachments(message)

    def test_has_no_attachments(self, generator: GemstoneGenerator, build_message_from_payload):
        message = build_message_from_payload(
            generator,
            ChatCompletionRequest(
                messages=[
                    UserMessage(content=ArrayOfContentParts(root=[TextContentPart(text="Hello")])),
                    AssistantMessage(content="Hi there!"),
                    UserMessage(content="Hello world!"),  # Non-dict content
                ]
            ),
        )
        assert not LLMAgentUtils.has_attachments(message)

    def test_has_attachments_with_later_messages(self, generator: GemstoneGenerator, build_message_from_payload):
        message = build_message_from_payload(
            generator,
            ChatCompletionRequest(
                messages=[
                    UserMessage(content="Hello"),
                    AssistantMessage(content="Hi there!"),
                    UserMessage(content="Hello world!"),  # Non-dict content
                    UserMessage(
                        content=ArrayOfContentParts(
                            root=[
                                FileContentPart(file_url=FileUrl(url="http://example.com/file2")),
                            ]
                        )
                    ),
                ]
            ),
        )
        assert LLMAgentUtils.has_attachments(message)

    def test_no_user_messages(self, generator: GemstoneGenerator, build_message_from_payload):
        message = build_message_from_payload(
            generator,
            ChatCompletionRequest(
                messages=[
                    AssistantMessage(content="Hi there!"),
                    SystemMessage(content="System message"),
                ]
            ),
        )
        assert not LLMAgentUtils.has_attachments(message)

    def test_empty_payload(self, generator: GemstoneGenerator, build_message_from_payload):
        # Provide raw dict to bypass Pydantic min_length=1 on messages
        message = build_message_from_payload(
            generator,
            {"messages": []},
            format=get_qualified_class_name(ChatCompletionRequest),
        )
        assert not LLMAgentUtils.has_attachments(message)

    def test_no_messages_key(self, generator: GemstoneGenerator, build_message_from_payload):
        message = build_message_from_payload(
            generator,
            {"foo": "bar"},  # payload lacks 'messages' key
            format=get_qualified_class_name(ChatCompletionRequest),
        )
        assert not LLMAgentUtils.has_attachments(message)

    def test_image_attachments(self, generator: GemstoneGenerator, build_message_from_payload):
        message = build_message_from_payload(
            generator,
            ChatCompletionRequest(
                messages=[
                    UserMessage(
                        content=ArrayOfContentParts(
                            root=[
                                ImageContentPart(image_url=ImageUrl(url="http://example.com/image1")),
                                TextContentPart(text="Hello"),
                            ]
                        )
                    ),
                    AssistantMessage(content="Hi there!"),
                    UserMessage(content="Hello world!"),
                ]
            ),
        )
        assert LLMAgentUtils.has_attachments(message)

    def test_filter_attachments(self):
        payload = ChatCompletionRequest(
            messages=[
                UserMessage(
                    content=ArrayOfContentParts(
                        root=[
                            FileContentPart(file_url=FileUrl(url="http://example.com/file1")),
                            TextContentPart(text="Hello"),
                        ]
                    )
                ),
                AssistantMessage(content="Hi there!"),
                UserMessage(content="Hello world!"),
            ]
        )
        filtered_payload = LLMAgentUtils.filter_attachments(payload, keep_http_attachments=False)
        assert len(filtered_payload.messages) == 3
        assert isinstance(filtered_payload.messages[0], UserMessage)
        assert isinstance(filtered_payload.messages[1], AssistantMessage)
        assert isinstance(filtered_payload.messages[2], UserMessage)
        # First user message should retain only non-attachment parts inside ArrayOfContentParts
        first_user = filtered_payload.messages[0]
        assert isinstance(first_user.content, ArrayOfContentParts)
        assert len(first_user.content.root) == 1
        assert isinstance(first_user.content.root[0], TextContentPart)
        assert first_user.content.root[0].text == "Hello"
        # Plain text user message should be preserved as-is
        assert filtered_payload.messages[2].content == "Hello world!"

    def test_filter_attachments_only_attachments_left_empty(self):
        payload = ChatCompletionRequest(
            messages=[
                UserMessage(
                    content=ArrayOfContentParts(
                        root=[
                            FileContentPart(file_url=FileUrl(url="http://example.com/file1")),
                            ImageContentPart(image_url=ImageUrl(url="http://example.com/image1")),
                        ]
                    )
                ),
                AssistantMessage(content="Hi there!"),
            ]
        )
        filtered_payload = LLMAgentUtils.filter_attachments(payload, keep_http_attachments=False)
        assert len(filtered_payload.messages) == 2
        assert isinstance(filtered_payload.messages[0], UserMessage)
        assert isinstance(filtered_payload.messages[1], AssistantMessage)
        # First user message should now contain empty string (attachments removed)
        first_user = filtered_payload.messages[0]
        assert first_user.content == ""

    def test_filter_attachments_mixed_multiple_texts(self):
        payload = ChatCompletionRequest(
            messages=[
                UserMessage(
                    content=ArrayOfContentParts(
                        root=[
                            TextContentPart(text="Part A"),
                            FileContentPart(file_url=FileUrl(url="http://example.com/file1")),
                            TextContentPart(text="Part B"),
                            ImageContentPart(image_url=ImageUrl(url="http://example.com/image1")),
                        ]
                    )
                ),
            ]
        )
        filtered_payload = LLMAgentUtils.filter_attachments(payload, keep_http_attachments=False)
        assert len(filtered_payload.messages) == 1
        first_user = filtered_payload.messages[0]
        assert isinstance(first_user.content, ArrayOfContentParts)
        assert [p.text for p in first_user.content.root if isinstance(p, TextContentPart)] == [
            "Part A",
            "Part B",
        ]

    def test_filter_attachments_multiple_user_messages_mixed(self):
        payload = ChatCompletionRequest(
            messages=[
                UserMessage(content="Plain one"),
                AssistantMessage(content="Ack"),
                UserMessage(
                    content=ArrayOfContentParts(
                        root=[
                            TextContentPart(text="T1"),
                            FileContentPart(file_url=FileUrl(url="http://example.com/fileA")),
                        ]
                    )
                ),
                UserMessage(
                    content=ArrayOfContentParts(
                        root=[
                            ImageContentPart(image_url=ImageUrl(url="http://example.com/img")),
                            TextContentPart(text="T2"),
                        ]
                    )
                ),
                AssistantMessage(content="Done"),
            ]
        )
        filtered_payload = LLMAgentUtils.filter_attachments(payload, keep_http_attachments=False)
        assert len(filtered_payload.messages) == 5
        # 1st message preserved plain string
        assert isinstance(filtered_payload.messages[0], UserMessage)
        assert filtered_payload.messages[0].content == "Plain one"
        # 2nd assistant unchanged
        assert isinstance(filtered_payload.messages[1], AssistantMessage)
        assert filtered_payload.messages[1].content == "Ack"
        # 3rd user retains only text part in ArrayOfContentParts
        m2 = filtered_payload.messages[2]
        assert isinstance(m2.content, ArrayOfContentParts)
        assert len(m2.content.root) == 1 and isinstance(m2.content.root[0], TextContentPart)
        assert m2.content.root[0].text == "T1"
        # 4th user retains only text part in ArrayOfContentParts
        m3 = filtered_payload.messages[3]
        assert isinstance(m3.content, ArrayOfContentParts)
        assert len(m3.content.root) == 1 and isinstance(m3.content.root[0], TextContentPart)
        assert m3.content.root[0].text == "T2"
        # 5th assistant unchanged
        assert isinstance(filtered_payload.messages[4], AssistantMessage)
        assert filtered_payload.messages[4].content == "Done"

    def test_filter_attachments_preserve_order_and_roles(self):
        payload = ChatCompletionRequest(
            messages=[
                SystemMessage(content="sys"),
                UserMessage(
                    content=ArrayOfContentParts(
                        root=[
                            TextContentPart(text="A1"),
                            ImageContentPart(image_url=ImageUrl(url="http://x/img1")),
                            TextContentPart(text="A2"),
                        ]
                    )
                ),
                AssistantMessage(content="assist"),
                UserMessage(content="B1"),
            ]
        )
        filtered_payload = LLMAgentUtils.filter_attachments(payload, keep_http_attachments=False)
        roles = [m.role for m in filtered_payload.messages]
        assert roles == [
            SystemMessage(role="system", content="sys").role,
            UserMessage(
                content=ArrayOfContentParts(root=[TextContentPart(text="A1"), TextContentPart(text="A2")])
            ).role,
            AssistantMessage(content="assist").role,
            UserMessage(content="B1").role,
        ]
        # Check user array preserved order of remaining text parts
        arr_msg = filtered_payload.messages[1]
        assert isinstance(arr_msg.content, ArrayOfContentParts)
        assert [p.text for p in arr_msg.content.root if isinstance(p, TextContentPart)] == [
            "A1",
            "A2",
        ]

    def test_filter_attachments_empty_array_remains_empty(self):
        payload = ChatCompletionRequest(
            messages=[
                UserMessage(
                    content=ArrayOfContentParts(
                        root=[
                            FileContentPart(file_url=FileUrl(url="http://example.com/fileA")),
                        ]
                    )
                ),
                AssistantMessage(content="ok"),
            ]
        )
        filtered_payload = LLMAgentUtils.filter_attachments(payload, keep_http_attachments=False)
        assert len(filtered_payload.messages) == 2
        assert isinstance(filtered_payload.messages[0], UserMessage)
        assert filtered_payload.messages[0].content == ""
        assert isinstance(filtered_payload.messages[1], AssistantMessage)

    def test_filter_attachments_keep_http_true_keeps_http(self):
        payload = ChatCompletionRequest(
            messages=[
                UserMessage(
                    content=ArrayOfContentParts(
                        root=[
                            TextContentPart(text="Hello"),
                            FileContentPart(file_url=FileUrl(url="http://example.com/file1")),
                            ImageContentPart(image_url=ImageUrl(url="http://example.com/image1")),
                        ]
                    )
                )
            ]
        )
        filtered_payload = LLMAgentUtils.filter_attachments(payload, keep_http_attachments=True)
        assert len(filtered_payload.messages) == 1
        first_user = filtered_payload.messages[0]
        assert isinstance(first_user.content, ArrayOfContentParts)
        parts = first_user.content.root
        # All three parts should remain: text + file + image (http)
        assert len(parts) == 3
        assert any(isinstance(p, TextContentPart) and p.text == "Hello" for p in parts)
        assert any(isinstance(p, FileContentPart) for p in parts)
        assert any(isinstance(p, ImageContentPart) for p in parts)

    def test_filter_attachments_keep_http_true_keeps_https(self):
        payload = ChatCompletionRequest(
            messages=[
                UserMessage(
                    content=ArrayOfContentParts(
                        root=[
                            TextContentPart(text="Hello"),
                            FileContentPart(file_url=FileUrl(url="https://example.com/file1")),
                            ImageContentPart(image_url=ImageUrl(url="https://example.com/image1")),
                        ]
                    )
                )
            ]
        )
        filtered_payload = LLMAgentUtils.filter_attachments(payload, keep_http_attachments=True)
        assert len(filtered_payload.messages) == 1
        first_user = filtered_payload.messages[0]
        assert isinstance(first_user.content, ArrayOfContentParts)
        parts = first_user.content.root
        # All three parts should remain: text + file + image (https)
        assert len(parts) == 3
        assert any(isinstance(p, TextContentPart) and p.text == "Hello" for p in parts)
        assert any(isinstance(p, FileContentPart) for p in parts)
        assert any(isinstance(p, ImageContentPart) for p in parts)

    def test_filter_with_mixed_attachments(self):
        # Mix of http/https (should be kept when flag=True) and non-http (ftp) attachments
        payload = ChatCompletionRequest(
            messages=[
                UserMessage(
                    content=ArrayOfContentParts(
                        root=[
                            TextContentPart(text="Keep"),
                            FileContentPart(file_url=FileUrl(url="http://example.com/file_http")),
                            ImageContentPart(image_url=ImageUrl(url="https://example.com/image_https")),
                            FileContentPart(file_url=FileUrl(url="ftp://example.com/file_ftp")),
                            ImageContentPart(image_url=ImageUrl(url="ftp://example.com/image_ftp")),
                        ]
                    )
                )
            ]
        )

        # keep_http_attachments=True should keep text + http file + https image (in order), drop ftp ones
        filtered_keep_http = LLMAgentUtils.filter_attachments(payload, keep_http_attachments=True)
        assert len(filtered_keep_http.messages) == 1
        msg = filtered_keep_http.messages[0]
        assert isinstance(msg, UserMessage)
        assert isinstance(msg.content, ArrayOfContentParts)
        parts = msg.content.root
        assert len(parts) == 3
        assert isinstance(parts[0], TextContentPart) and parts[0].text == "Keep"
        assert isinstance(parts[1], FileContentPart) and str(parts[1].file_url.url).startswith("http")
        assert isinstance(parts[2], ImageContentPart) and str(parts[2].image_url.url).startswith("https")

        # keep_http_attachments=False should remove all attachments and keep only text
        filtered_remove_all = LLMAgentUtils.filter_attachments(payload, keep_http_attachments=False)
        assert len(filtered_remove_all.messages) == 1
        msg2 = filtered_remove_all.messages[0]
        assert isinstance(msg2.content, ArrayOfContentParts)
        parts2 = msg2.content.root
        assert len(parts2) == 1 and isinstance(parts2[0], TextContentPart) and parts2[0].text == "Keep"
