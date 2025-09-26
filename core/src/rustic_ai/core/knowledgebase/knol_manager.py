from datetime import datetime
from hashlib import sha256
import json
import logging
from typing import Literal, Optional, Tuple
from urllib.parse import urlparse

from fsspec.implementations.dirfs import DirFileSystem as FileSystem
from pydantic import BaseModel

from rustic_ai.core.agents.commons.media import MediaLink
from rustic_ai.core.knowledgebase.model import Knol, Provenance

from .knol_utils import KnolUtils

# ======================= Status models =======================


class CatalogStatus(BaseModel):
    status: Literal["stored", "failed", "indexing", "indexed", "retrieved", "deleted"]
    message: str


class CatalogStatusStored(CatalogStatus):
    status: Literal["stored"] = "stored"
    knol: Optional[Knol] = None
    message: str = "Catalog stored"


class CatalogStatusFailed(CatalogStatus):
    status: Literal["failed"] = "failed"
    error: str
    message: str = "Action failed"
    action: Literal["catalog", "retrieve", "search", "index", "delete"]


class CatalogStatusRetrieved(CatalogStatus):
    status: Literal["retrieved"] = "retrieved"
    knol: Optional[Knol] = None
    message: str = "Catalog retrieved"


class CatalogStatusDeleted(CatalogStatus):
    status: Literal["deleted"] = "deleted"
    knol_id: str
    message: str = "Catalog deleted"


class CatalogStatusIndexing(CatalogStatus):
    status: Literal["indexing"] = "indexing"
    knol: Optional[Knol] = None
    message: str = "Catalog indexing in progress"


class KnolManager:
    """
    Async-only helper for storing/retrieving knols on an fsspec filesystem.

    Assumes `filesystem` was created with `asynchronous=True` and is an AsyncFileSystem
    (or a DirFileSystem wrapping one). Uses ONLY underscore async methods; no sync fallbacks.
    """

    # Tune this if needed; 8–16 MiB is typical for cloud object stores
    CHUNK_SIZE: int = 8 * 1024 * 1024

    def __init__(self, filesystem: FileSystem, location: str = "library"):
        assert getattr(filesystem, "asynchronous", False), "Filesystem must be created with asynchronous=True"
        self.filesystem = filesystem
        self.location = location
        # __init__ is sync; creating the base directory synchronously is fine
        self.filesystem.makedirs(self.location, exist_ok=True)
        self.url = f"file:///{self.location}"

    # ---------------- internal utilities ----------------

    @staticmethod
    def _meta_sidecar_for(path: str) -> str:
        # "<dir>/<file>" -> "<dir>/.<file>.meta"
        if "/" in path:
            dirname, filename = path.rsplit("/", 1)
            return f"{dirname}/.{filename}.meta"
        return f".{path}.meta"

    @staticmethod
    def _knol_sidecar_for(path: str) -> str:
        # "<dir>/<file>" -> "<dir>/.<file>.knol"
        if "/" in path:
            dirname, filename = path.rsplit("/", 1)
            return f"{dirname}/.{filename}.knol"
        return f".{path}.knol"

    async def _read_text(self, path: str) -> str:
        # Prefer _cat_file; fall back to _cat
        if hasattr(self.filesystem, "_cat_file"):
            data = await self.filesystem._cat_file(path)  # bytes
        else:
            data = await self.filesystem._cat(path)  # bytes
        return data.decode("utf-8")

    async def _read_json(self, path: str) -> dict:
        return json.loads(await self._read_text(path))

    async def _file_size_and_hash(self, path: str) -> Tuple[int, str]:
        """
        Compute (size_in_bytes, sha256_hex) without loading the whole file into memory.
        Uses ranged `_cat_file(..., start=..., end=...)` when available; otherwise
        falls back once to a single `_cat`/`_cat_file` read.
        """
        size = None
        try:
            info = await self.filesystem._info(path)
            if info and "size" in info and info["size"] is not None:
                size = int(info["size"])
        except Exception:
            # If _info fails, we will fall back to full read below
            pass

        has_cat_file = hasattr(self.filesystem, "_cat_file")
        h = sha256()

        if has_cat_file and size is not None and size > self.CHUNK_SIZE:
            # Attempt ranged reads
            offset = 0
            supports_range = True

            while offset < size:
                to_read = min(self.CHUNK_SIZE, size - offset)
                try:
                    # Use inclusive end typical for HTTP/S3 range headers
                    data = await self.filesystem._cat_file(path, start=offset, end=offset + to_read - 1)
                except TypeError:
                    # Backend does not accept start/end params
                    supports_range = False
                    break

                # If the backend ignored ranges and returned an unexpectedly large chunk,
                # drop to full-read fallback.
                if len(data) > to_read * 2:
                    supports_range = False
                    break

                h.update(data[:to_read])
                offset += to_read

            if supports_range:
                return size, h.hexdigest().lower()
            # else: fall through to full-read fallback

        # Fallbacks: single full read (still async)
        if has_cat_file:
            data = await self.filesystem._cat_file(path)
        else:
            data = await self.filesystem._cat(path)

        h.update(data)
        return len(data), h.hexdigest().lower()

    async def _gather_meta_for_path(self, path: str, medialink: MediaLink) -> dict:
        """
        Collect metadata for `path`:
        - load sidecar JSON if present
        - fill name/mime/encoding from sidecar or medialink or filename
        - compute size_in_bytes + content_hash if missing (chunked)
        Returns a dict with keys: name, mime, encoding, size_in_bytes, content_hash, and any extra sidecar keys.
        """
        # must exist
        if not await self.filesystem._exists(path):
            raise FileNotFoundError(f"File {medialink.url} not found in the filesystem.")

        # load sidecar if present
        sidecar = {}
        meta_path = self._meta_sidecar_for(path)
        if await self.filesystem._exists(meta_path):
            try:
                sidecar = await self._read_json(meta_path)
            except Exception as e:
                logging.error("Failed reading sidecar meta for %s: %s", path, e)

        # fill fields
        filename = path.rsplit("/", 1)[-1] if "/" in path else path
        name = sidecar.get("name") or medialink.name or filename
        mimetype = sidecar.get("mimetype") or medialink.mimetype
        encoding = sidecar.get("encoding") or medialink.encoding

        size_in_bytes = sidecar.get("size_in_bytes")
        content_hash = sidecar.get("content_hash")
        if size_in_bytes is None or content_hash is None:
            size_in_bytes, content_hash = await self._file_size_and_hash(path)

        return {
            **sidecar,  # keep any extra fields users may stash
            "name": name,
            "mimetype": mimetype,
            "encoding": encoding,
            "size_in_bytes": int(size_in_bytes),
            "content_hash": content_hash,
        }

    async def _knol_from_media_link(self, medialink: MediaLink) -> Knol:
        # Initialize backend session if present (e.g., aiohttp/s3/gcs clients)
        base_fs = getattr(self.filesystem, "fs", self.filesystem)
        set_session = getattr(base_fs, "set_session", None)
        if callable(set_session):
            await set_session()

        # Resolve source path (supports file:/// or bare paths)
        parsed = urlparse(medialink.url)
        if parsed.scheme and parsed.scheme != "file":
            raise ValueError(
                "KnolHelper expects filesystem-backed MediaLinks (file:/// or plain paths). "
                f"Got scheme={parsed.scheme!r}"
            )
        path = parsed.path

        # Gather effective metadata (sidecar + fallbacks)
        meta = await self._gather_meta_for_path(path, medialink)

        mimetype = medialink.mimetype or meta.get("mimetype")
        metaparts = KnolUtils.create_metaparts_for_mime(mimetype, meta)

        # Build the Knol directly (no MediaLink mutation)
        knol_id = f"{meta['content_hash']}"  # id policy: just the hash (your current choice)

        source_uri = medialink.url if medialink.url.startswith("file://") else f"file://{medialink.url}"

        prov_props = {}
        for key in Provenance.model_fields.keys():
            if key in meta:
                prov_props[key] = meta[key]

        if "source_uri" not in prov_props:
            prov_props["source_uri"] = source_uri

        provenance = meta.get("provenance", Provenance(**prov_props))

        knol_props = {}

        for key in Knol.model_fields.keys():
            if key in meta:
                knol_props[key] = meta[key]

        created_at = meta.get("created_at")
        if created_at:
            try:
                knol_props["created_at"] = (
                    datetime.fromisoformat(created_at) if isinstance(created_at, str) else created_at
                )
            except Exception as e:
                logging.error("Failed to parse created_at: %s", e)
                knol_props["created_at"] = datetime.utcnow()

        updated_at = meta.get("updated_at")
        if updated_at:
            try:
                knol_props["updated_at"] = (
                    datetime.fromisoformat(updated_at) if isinstance(updated_at, str) else updated_at
                )
            except Exception as e:
                logging.error("Failed to parse updated_at: %s", e)
                knol_props["updated_at"] = datetime.utcnow()

        knol_props["id"] = knol_id
        knol_props["provenance"] = provenance
        knol_props["metaparts"] = metaparts
        knol_props["mimetype"] = mimetype

        knol = Knol(**knol_props)

        # Destination paths (per-knol directory layout)
        origin_media_meta_path = self._meta_sidecar_for(path)
        media_meta_exists = await self.filesystem._exists(origin_media_meta_path)
        if not media_meta_exists:
            logging.warning("Metadata file for media %s not found.", medialink.url)

        knol_dir = f"{self.location}/{knol_id}"
        content_path = f"{knol_dir}/content"
        media_meta_path = f"{knol_dir}/.meta"
        knol_meta_path = f"{knol_dir}/.knol"
        knol_meta_json = knol.model_dump_json()

        # Ensure destination directory exists
        self.filesystem.makedirs(knol_dir, exist_ok=True)

        # Write payload + sidecars atomically
        with self.filesystem.transaction:
            await self.filesystem._copy(path, content_path)

            # store/propagate media sidecar next to the stored payload:
            # if a source sidecar existed, copy it; else synthesize one from `meta`
            if media_meta_exists:
                await self.filesystem._copy(origin_media_meta_path, media_meta_path)
            else:
                await self.filesystem._pipe_file(
                    media_meta_path,
                    json.dumps(meta, ensure_ascii=False).encode("utf-8"),
                )

            # write knol sidecar
            await self.filesystem._pipe_file(knol_meta_path, knol_meta_json.encode("utf-8"))

        return knol

    # ---------------- public API (all async) ----------------

    async def catalog_medialink(self, media: MediaLink) -> CatalogStatusStored | CatalogStatusFailed:
        try:
            knol = await self._knol_from_media_link(media)
            return CatalogStatusStored(knol=knol)
        except Exception as e:
            logging.exception("Failed to catalog media:")
            return CatalogStatusFailed(error=str(e), action="catalog")

    async def retrieve(self, knol_id: str) -> CatalogStatusRetrieved | CatalogStatusFailed:
        try:
            # Async read of knol metadata via KnolUtils
            knol = await KnolUtils.read_knol_from_library(self.filesystem, self.location, knol_id)
            return CatalogStatusRetrieved(knol=knol)
        except Exception as e:
            logging.exception("Failed to retrieve media:")
            return CatalogStatusFailed(
                message=f"Knol [id={knol_id}] retrieval failed",
                error=str(e),
                action="retrieve",
            )

    async def delete(self, knol_id: str) -> CatalogStatusDeleted | CatalogStatusFailed:
        """
        Remove the stored payload and both sidecars, idempotently (no MediaUtils).
        """
        try:
            knol_dir = f"{self.location}/{knol_id}"

            logging.info("Deleting knol directory: %s", knol_id)

            if not await self.filesystem._exists(knol_dir):
                return CatalogStatusFailed(
                    message=f"Knol [id={knol_id}] deletion failed",
                    error="not found",
                    action="delete",
                )

            with self.filesystem.transaction:
                # Remove directory recursively
                await self.filesystem._rm(knol_dir, recursive=True)
            return CatalogStatusDeleted(knol_id=knol_id)
        except Exception as e:
            logging.exception("Failed to delete media:")
            return CatalogStatusFailed(
                message=f"Knol [id={knol_id}] deletion failed",
                error=str(e),
                action="delete",
            )
