from hashlib import sha256

from fsspec.implementations.dirfs import DirFileSystem as FileSystem
import pytest

from rustic_ai.core.agents.commons.media import Document, MediaLink, MediaUtils
from rustic_ai.core.guild.agent_ext.depends.filesystem.filesystem import (
    FileSystemResolver,
)
from rustic_ai.core.knowledgebase.knol_manager import KnolManager


@pytest.fixture
def text_media():
    return Document(
        name="example.txt",
        mimetype="text/plain",
        encoding="utf-8",
        content="This is an example document.",
        metadata={
            "author": "Test User",
            "description": "A simple text document.",
            "tags": ["example", "test", "document"],
            "language": "en",
            "page_count": 1,
        },
    )


@pytest.fixture
def filesystem(tmp_path):
    fsr = FileSystemResolver(
        path_base=str(tmp_path),
        protocol="file",
        storage_options={},
        asynchronous=True,
    )

    return fsr.resolve("test_guild", "test_agent")


@pytest.fixture
def media_link(text_media: Document, filesystem: FileSystem):

    # First, save the media to the filesystem to get a file path
    filesystem.makedirs("media", exist_ok=True)
    MediaUtils.save_media_to_file(filesystem, text_media, dir="media", filename=text_media.name)
    file_path = f"media/{text_media.name}"

    return MediaUtils.medialink_from_file(filesystem, f"file:///{file_path}")


@pytest.fixture
def librarian(filesystem):
    return KnolManager(filesystem)


class TestKnolManager:

    @pytest.mark.asyncio
    async def test_catalog_from_media_link(
        self, text_media: Document, media_link: MediaLink, filesystem, librarian: KnolManager
    ):
        hash = sha256(text_media.content.encode(media_link.encoding or "utf-8"))

        id_from_content = f"{hash.hexdigest().lower()}"

        status = await librarian.catalog_medialink(media_link)

        assert status.status == "stored"

        knol = status.knol
        assert knol is not None

        assert knol.id == id_from_content
        assert knol.name == "example.txt"
        assert knol.mimetype == "text/plain"
        assert knol.size_in_bytes == len(text_media.content.encode("utf-8"))
        assert knol.language == "en"
        assert len(knol.metaparts) == 3
        assert knol.metaparts[0].kind == "common"
        assert knol.metaparts[0].description == "A simple text document."
        assert knol.metaparts[0].author == "Test User"

        assert "example" in knol.metaparts[0].tags
        assert "test" in knol.metaparts[0].tags
        assert "document" in knol.metaparts[0].tags

        assert knol.metaparts[1].kind == "document"
        assert knol.metaparts[1].page_count == 1

        assert knol.metaparts[2].kind == "extra"

    @pytest.mark.asyncio
    async def test_catalog_failure(self, filesystem: FileSystem, librarian: KnolManager):
        # Create a MediaLink that points to a non-existent file
        bad_media_link = MediaLink(
            id="bad-link",
            name="nonexistent.txt",
            url="file:///media/nonexistent.txt",
            mimetype="text/plain",
            metadata={},
            on_filesystem=True,
            encoding="utf-8",
        )

        status = await librarian.catalog_medialink(bad_media_link)

        assert status.status == "failed"
        assert status.action == "catalog"
        assert "No such file" in status.error or "not found" in status.error.lower()

    @pytest.mark.asyncio
    async def test_retrieve(self, media_link: MediaLink, librarian: KnolManager):
        status = await librarian.catalog_medialink(media_link)
        assert status.status == "stored"

        retrieved = await librarian.retrieve(status.knol.id)
        assert retrieved is not None
        assert retrieved.status == "retrieved"
        assert retrieved.knol is not None

        knol = retrieved.knol
        assert knol.id == status.knol.id
        assert knol.name == "example.txt"
        assert knol.mimetype == "text/plain"
        assert knol.size_in_bytes == media_link.size_in_bytes
        assert knol.language == "en"
        assert len(knol.metaparts) == 3
        assert knol.metaparts[0].kind == "common"
        assert knol.metaparts[0].description == "A simple text document."
        assert "example" in knol.metaparts[0].tags
        assert "test" in knol.metaparts[0].tags
        assert "document" in knol.metaparts[0].tags

        assert knol.metaparts[1].kind == "document"
        assert knol.metaparts[1].page_count == 1
        assert knol.metaparts[0].author == "Test User"

        assert knol.metaparts[2].kind == "extra"

    @pytest.mark.asyncio
    async def test_retrieve_not_found(self, librarian: KnolManager):
        retrieved = await librarian.retrieve("nonexistent-id")
        assert retrieved is not None
        assert retrieved.status == "failed"
        assert retrieved.action == "retrieve"
        assert retrieved.message == "Knol [id=nonexistent-id] retrieval failed"
        assert "not found" in retrieved.error.lower()
        assert "nonexistent-id" in retrieved.message

    @pytest.mark.asyncio
    async def test_retrieve_invalid_id(self, librarian: KnolManager):
        retrieved = await librarian.retrieve("")
        assert retrieved is not None
        assert retrieved.status == "failed"
        assert retrieved.action == "retrieve"
        assert retrieved.message == "Knol [id=] retrieval failed"
        assert "invalid" in retrieved.error.lower() or "not found" in retrieved.error.lower()

    @pytest.mark.asyncio
    async def test_delete(self, media_link: MediaLink, librarian: KnolManager):
        status = await librarian.catalog_medialink(media_link)
        assert status.status == "stored"

        deleted = await librarian.delete(status.knol.id)
        assert deleted is not None
        assert deleted.status == "deleted"
        assert deleted.knol_id == status.knol.id

        # Try to retrieve after deletion
        retrieved = await librarian.retrieve(status.knol.id)
        assert retrieved is not None
        assert retrieved.status == "failed"
        assert retrieved.action == "retrieve"
        assert retrieved.message == f"Knol [id={status.knol.id}] retrieval failed"
        assert "not found" in retrieved.error.lower()

    @pytest.mark.asyncio
    async def test_delete_not_found(self, librarian: KnolManager):
        deleted = await librarian.delete("nonexistent-id")
        assert deleted is not None
        assert deleted.status == "failed"
        assert deleted.action == "delete"
        assert deleted.message == "Knol [id=nonexistent-id] deletion failed"
        assert "not found" in deleted.error.lower()
        assert "nonexistent-id" in deleted.message
