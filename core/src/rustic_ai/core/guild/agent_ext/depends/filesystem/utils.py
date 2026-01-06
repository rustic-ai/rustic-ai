from fsspec.implementations.dirfs import DirFileSystem as FileSystem


def get_root_uri(dirfs: FileSystem) -> str:
    """Get the fully-qualified root URI of the DirFileSystem.

    Args:
        dirfs: A DirFileSystem instance

    Returns:
        The root URI with protocol (e.g. 's3://bucket/prefix/')
    """
    return dirfs.fs.unstrip_protocol(dirfs.path)


def get_uri(dirfs: FileSystem, p: str) -> str:
    """Get the fully-qualified URI for a path within the DirFileSystem.

    Args:
        dirfs: A DirFileSystem instance
        p: A relative or absolute path to resolve within the DirFileSystem

    Returns:
        The fully-qualified URI with protocol (e.g. 's3://bucket/prefix/path')
    """
    # Strip *underlying* protocol (e.g. s3://) if someone passes it
    rel = dirfs.fs._strip_protocol(p)  # underlying fs, not dirfs
    # Treat leading separators as "relative to the dirfs root"
    rel = rel.lstrip(dirfs.fs.sep)  # prevents bucket/prefix//tmp

    joined = dirfs.fs.sep.join((dirfs.path, rel))  # dirfs.path is already protocol-stripped
    # Turn back into a fully-qualified URI like s3://...
    return dirfs.fs.unstrip_protocol(joined)
