__all__ = ("__version__", "version_info")

from pbr.version import VersionInfo

_v = VersionInfo("d4science_hub").semantic_version()
__version__ = _v.release_string()
version_info = _v.version_tuple()
