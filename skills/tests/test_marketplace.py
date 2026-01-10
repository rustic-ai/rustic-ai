"""Tests for skills marketplace."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from rustic_ai.skills.marketplace import (
    MarketplaceError,
    SkillMarketplace,
)
from rustic_ai.skills.models import SkillSource


class TestSkillMarketplace:
    """Tests for SkillMarketplace class."""

    def test_init_default(self):
        """Test initialization with defaults."""
        marketplace = SkillMarketplace()

        assert marketplace.install_path == Path("/tmp/rustic-skills")
        assert "anthropic" in marketplace.registry.sources

    def test_init_custom_paths(self, temp_dir):
        """Test initialization with custom paths."""
        install_path = temp_dir / "install"
        cache_path = temp_dir / "cache"

        marketplace = SkillMarketplace(
            install_path=install_path,
            cache_path=cache_path,
        )

        assert marketplace.install_path == install_path
        assert marketplace.cache_path == cache_path

    def test_add_source(self):
        """Test adding a source."""
        marketplace = SkillMarketplace()
        marketplace.add_source(
            name="custom",
            source_type="github",
            location="owner/repo",
            branch="develop",
            skills_path="src/skills",
        )

        assert "custom" in marketplace.registry.sources
        source = marketplace.registry.sources["custom"]
        assert source.location == "owner/repo"
        assert source.branch == "develop"
        assert source.skills_path == "src/skills"

    def test_list_sources(self):
        """Test listing sources."""
        marketplace = SkillMarketplace()
        sources = marketplace.list_sources()

        # Should have at least the known sources
        assert len(sources) >= 1
        names = [s.name for s in sources]
        assert "anthropic" in names

    def test_discover_from_local(self, skills_collection_dir):
        """Test discovering skills from local directory."""
        marketplace = SkillMarketplace()
        marketplace.add_source(
            name="local",
            source_type="local",
            location=str(skills_collection_dir),
            skills_path="",  # skills are at root level
        )

        discovered = marketplace.discover("local")

        # Should find skill-one and skill-two (but not not-a-skill)
        assert len(discovered) == 2
        names = [s.name for s in discovered]
        assert "test-skill" in names
        assert "minimal-skill" in names

    def test_discover_from_local_with_skills_path(self, temp_dir, sample_skill_md):
        """Test discovering skills from local source with skills_path."""
        repo_dir = temp_dir / "repo"
        skills_dir = repo_dir / "skills"
        skill_dir = skills_dir / "test-skill"

        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(sample_skill_md)

        marketplace = SkillMarketplace()
        marketplace.add_source(
            name="local",
            source_type="local",
            location=str(repo_dir),
            skills_path="skills",
        )

        discovered = marketplace.discover("local")

        assert len(discovered) == 1
        assert discovered[0].name == "test-skill"

    def test_discover_from_local_not_found(self, temp_dir):
        """Test error when local source doesn't exist."""
        marketplace = SkillMarketplace()
        marketplace.add_source(
            name="nonexistent",
            source_type="local",
            location=str(temp_dir / "does-not-exist"),
        )

        # Should not raise but return empty list (with warning logged)
        discovered = marketplace.discover("nonexistent")
        assert len(discovered) == 0

    def test_install_from_local(self, skills_collection_dir, temp_dir):
        """Test installing a skill from local source."""
        install_path = temp_dir / "installed"

        marketplace = SkillMarketplace(install_path=install_path)
        marketplace.add_source(
            name="local",
            source_type="local",
            location=str(skills_collection_dir),
            skills_path="",
        )

        # Discover first
        marketplace.discover("local")

        # Install
        path = marketplace.install("test-skill")

        assert path.exists()
        assert (path / "SKILL.md").exists()

    def test_install_skill_not_found(self, temp_dir):
        """Test error when skill not found."""
        marketplace = SkillMarketplace(install_path=temp_dir / "install")
        marketplace.add_source(
            name="local",
            source_type="local",
            location=str(temp_dir),
            skills_path="",
        )

        with pytest.raises(MarketplaceError, match="not found"):
            marketplace.install("nonexistent-skill")

    def test_install_already_exists(self, skills_collection_dir, temp_dir):
        """Test error when skill already installed."""
        install_path = temp_dir / "installed"

        marketplace = SkillMarketplace(install_path=install_path)
        marketplace.add_source(
            name="local",
            source_type="local",
            location=str(skills_collection_dir),
            skills_path="",
        )

        marketplace.discover("local")
        marketplace.install("test-skill")

        # Try to install again
        with pytest.raises(MarketplaceError, match="already installed"):
            marketplace.install("test-skill")

    def test_install_force_overwrite(self, skills_collection_dir, temp_dir):
        """Test force overwrite existing installation."""
        install_path = temp_dir / "installed"

        marketplace = SkillMarketplace(install_path=install_path)
        marketplace.add_source(
            name="local",
            source_type="local",
            location=str(skills_collection_dir),
            skills_path="",
        )

        marketplace.discover("local")
        path1 = marketplace.install("test-skill")

        # Force reinstall
        path2 = marketplace.install("test-skill", force=True)

        assert path1 == path2
        assert path2.exists()

    def test_uninstall(self, skills_collection_dir, temp_dir):
        """Test uninstalling a skill."""
        install_path = temp_dir / "installed"

        marketplace = SkillMarketplace(install_path=install_path)
        marketplace.add_source(
            name="local",
            source_type="local",
            location=str(skills_collection_dir),
            skills_path="",
        )

        marketplace.discover("local")
        path = marketplace.install("test-skill")

        assert path.exists()

        marketplace.uninstall("test-skill")

        assert not path.exists()

    def test_uninstall_not_installed(self, temp_dir):
        """Test error when uninstalling non-installed skill."""
        marketplace = SkillMarketplace(install_path=temp_dir / "install")

        with pytest.raises(MarketplaceError, match="not installed"):
            marketplace.uninstall("nonexistent")

    def test_list_installed(self, skills_collection_dir, temp_dir):
        """Test listing installed skills."""
        install_path = temp_dir / "installed"

        marketplace = SkillMarketplace(install_path=install_path)
        marketplace.add_source(
            name="local",
            source_type="local",
            location=str(skills_collection_dir),
            skills_path="",
        )

        marketplace.discover("local")
        marketplace.install("test-skill")
        marketplace.install("minimal-skill")

        installed = marketplace.list_installed()

        assert len(installed) == 2
        names = [s.name for s in installed]
        assert "test-skill" in names
        assert "minimal-skill" in names

    def test_list_installed_empty(self, temp_dir):
        """Test listing installed skills when none installed."""
        marketplace = SkillMarketplace(install_path=temp_dir / "empty")
        installed = marketplace.list_installed()

        assert len(installed) == 0

    def test_get_installed_skill_path(self, skills_collection_dir, temp_dir):
        """Test getting path to installed skill."""
        install_path = temp_dir / "installed"

        marketplace = SkillMarketplace(install_path=install_path)
        marketplace.add_source(
            name="local",
            source_type="local",
            location=str(skills_collection_dir),
            skills_path="",
        )

        marketplace.discover("local")
        marketplace.install("test-skill")

        path = marketplace.get_installed_skill_path("test-skill")

        assert path is not None
        assert path.exists()
        assert (path / "SKILL.md").exists()

    def test_get_installed_skill_path_not_installed(self, temp_dir):
        """Test getting path when skill not installed."""
        marketplace = SkillMarketplace(install_path=temp_dir / "install")
        path = marketplace.get_installed_skill_path("nonexistent")

        assert path is None

    def test_search(self, skills_collection_dir, temp_dir):
        """Test searching for skills."""
        marketplace = SkillMarketplace(install_path=temp_dir / "install")
        marketplace.add_source(
            name="local",
            source_type="local",
            location=str(skills_collection_dir),
            skills_path="",
        )

        marketplace.discover("local")

        results = marketplace.search("test")
        assert len(results) >= 1

    @patch("rustic_ai.skills.marketplace.Repo")
    def test_discover_from_github(self, mock_repo, temp_dir):
        """Test discovering from GitHub (mocked)."""
        cache_path = temp_dir / "cache"
        install_path = temp_dir / "install"

        # Create the skill structure that clone_from would create
        def mock_clone_from(url, path, branch, depth):
            # Simulate what git clone would do
            path.mkdir(parents=True, exist_ok=True)
            skills_dir = path / "skills"
            skills_dir.mkdir()
            skill_dir = skills_dir / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                """---
name: test-skill
description: A GitHub skill
---

Instructions
"""
            )
            return MagicMock()

        mock_repo.clone_from.side_effect = mock_clone_from

        marketplace = SkillMarketplace(
            install_path=install_path,
            cache_path=cache_path,
        )

        discovered = marketplace.discover("anthropic")

        # Verify clone was attempted
        mock_repo.clone_from.assert_called_once()
        # Should have discovered the skill
        assert len(discovered) == 1
        assert discovered[0].name == "test-skill"

    def test_unknown_source_type(self, temp_dir):
        """Test error for unknown source type."""
        marketplace = SkillMarketplace(install_path=temp_dir / "install")
        marketplace.registry.add_source(
            SkillSource(
                name="unknown",
                type="ftp",  # unknown type
                location="ftp://example.com",
            )
        )

        # Should not raise but log warning and return empty
        discovered = marketplace.discover("unknown")
        assert len(discovered) == 0


class TestKnownSources:
    """Tests for known skill sources."""

    def test_anthropic_source(self):
        """Test Anthropic source configuration."""
        source = SkillMarketplace.KNOWN_SOURCES["anthropic"]

        assert source.name == "anthropic"
        assert source.type == "github"
        assert source.location == "anthropics/skills"
        assert source.branch == "main"
        assert source.skills_path == "skills"
