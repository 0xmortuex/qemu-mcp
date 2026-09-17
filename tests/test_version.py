"""Guards against qemu_mcp.__version__ drifting from the installed package's
own metadata (pyproject.toml's [project] version) - the two are independent
hardcoded strings in different files with nothing else checking they agree.
"""

import importlib.metadata

import qemu_mcp


def test_dunder_version_matches_installed_package_metadata():
    assert qemu_mcp.__version__ == importlib.metadata.version("qemu-mcp")
