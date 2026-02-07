"""Unit tests for version consistency."""

import importlib.metadata

import pytest

import genimg


@pytest.mark.unit
class TestVersionConsistency:
    """Test that version is consistently reported across the package."""

    def test_version_matches_package_metadata(self):
        """Verify genimg.__version__ matches installed package metadata."""
        # Get version from package metadata
        try:
            pkg_version = importlib.metadata.version("genimg")
        except importlib.metadata.PackageNotFoundError:
            # Package not installed (development mode without -e install)
            pytest.skip("Package not installed, can't verify metadata version")

        # Should match the __version__ attribute
        assert genimg.__version__ == pkg_version

    def test_version_format(self):
        """Verify version follows semantic versioning format."""
        version = genimg.__version__

        # Should be non-empty string
        assert isinstance(version, str)
        assert len(version) > 0

        # Should be either X.Y.Z format or development version
        if version.endswith(".dev"):
            # Development version (not installed)
            assert version == "0.0.0.dev"
        else:
            # Should have major.minor.patch format
            parts = version.split(".")
            assert len(parts) >= 2, f"Version {version} should have at least major.minor"

    def test_version_is_not_hardcoded_old_value(self):
        """Ensure we're not using the old hardcoded 0.1.0 version."""
        # This should never be 0.1.0 (the old hardcoded value)
        assert genimg.__version__ != "0.1.0", (
            "Version should be dynamically loaded from package metadata, not hardcoded to 0.1.0"
        )
