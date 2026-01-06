"""
Skill Marketplace for discovering and installing skills from various sources.

Supports:
- GitHub repositories (e.g., anthropics/skills)
- Local directories
- Git URLs
"""

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

import httpx
from git import Repo
from git.exc import GitCommandError

from .models import SkillMetadata, SkillRegistry, SkillSource
from .parser import SkillParser, SkillParseError

logger = logging.getLogger(__name__)


class MarketplaceError(Exception):
    """Raised when marketplace operations fail."""

    pass


class SkillMarketplace:
    """
    Marketplace for discovering and installing Agent Skills.

    Supports installing skills from:
    - GitHub repositories (sparse checkout for efficiency)
    - Local directories
    - Any Git URL

    Example usage:
        marketplace = SkillMarketplace()

        # Add Anthropic's official skills
        marketplace.add_source("anthropic", "github", "anthropics/skills")

        # Discover available skills
        marketplace.discover()

        # Install a specific skill
        marketplace.install("pdf")

        # List installed skills
        for skill in marketplace.list_installed():
            print(skill.name, skill.description)
    """

    # Well-known skill sources
    KNOWN_SOURCES = {
        "anthropic": SkillSource(
            name="anthropic",
            type="github",
            location="anthropics/skills",
            branch="main",
            skills_path="skills",
        ),
    }

    # Default installation directory
    DEFAULT_INSTALL_PATH = Path(".claude/skills")

    def __init__(
        self,
        install_path: Optional[Path] = None,
        cache_path: Optional[Path] = None,
    ):
        """
        Initialize the marketplace.

        Args:
            install_path: Where to install skills (default: .claude/skills)
            cache_path: Where to cache downloaded repos (default: temp directory)
        """
        self.install_path = Path(install_path) if install_path else self.DEFAULT_INSTALL_PATH
        self.cache_path = Path(cache_path) if cache_path else Path(tempfile.gettempdir()) / "rustic-skills-cache"

        self.registry = SkillRegistry()

        # Add known sources
        for source in self.KNOWN_SOURCES.values():
            self.registry.add_source(source)

    def add_source(
        self,
        name: str,
        source_type: str,
        location: str,
        branch: str = "main",
        skills_path: str = "skills",
    ):
        """
        Add a skill source to the marketplace.

        Args:
            name: Identifier for this source
            source_type: Type of source (github, local, git)
            location: GitHub repo (owner/repo), local path, or Git URL
            branch: Git branch (for github/git sources)
            skills_path: Path to skills folder within the source
        """
        source = SkillSource(
            name=name,
            type=source_type,
            location=location,
            branch=branch,
            skills_path=skills_path,
        )
        self.registry.add_source(source)

    def discover(self, source_name: Optional[str] = None) -> List[SkillMetadata]:
        """
        Discover available skills from sources.

        This loads only metadata (lazy loading) for efficient discovery.

        Args:
            source_name: Specific source to discover from, or None for all

        Returns:
            List of discovered skill metadata
        """
        sources = (
            [self.registry.sources[source_name]]
            if source_name
            else list(self.registry.sources.values())
        )

        discovered = []
        for source in sources:
            try:
                skills = self._discover_from_source(source)
                discovered.extend(skills)
            except Exception as e:
                logger.warning(f"Failed to discover from {source.name}: {e}")

        return discovered

    def _discover_from_source(self, source: SkillSource) -> List[SkillMetadata]:
        """Discover skills from a specific source."""
        if source.type == "github":
            return self._discover_from_github(source)
        elif source.type == "local":
            return self._discover_from_local(source)
        elif source.type == "git":
            return self._discover_from_git(source)
        else:
            raise MarketplaceError(f"Unknown source type: {source.type}")

    def _discover_from_github(self, source: SkillSource) -> List[SkillMetadata]:
        """Discover skills from a GitHub repository."""
        # Clone/update the repo
        repo_path = self._ensure_github_repo(source)

        # Discover skills in the skills folder
        skills_dir = repo_path / source.skills_path
        return self._discover_from_directory(skills_dir, source.name)

    def _discover_from_local(self, source: SkillSource) -> List[SkillMetadata]:
        """Discover skills from a local directory."""
        skills_dir = Path(source.location)
        if not skills_dir.exists():
            raise MarketplaceError(f"Local source not found: {source.location}")
        return self._discover_from_directory(skills_dir, source.name)

    def _discover_from_git(self, source: SkillSource) -> List[SkillMetadata]:
        """Discover skills from a Git URL."""
        repo_path = self._ensure_git_repo(source)
        skills_dir = repo_path / source.skills_path
        return self._discover_from_directory(skills_dir, source.name)

    def _discover_from_directory(self, skills_dir: Path, source_name: str) -> List[SkillMetadata]:
        """Discover skills from a directory containing skill folders."""
        if not skills_dir.exists():
            logger.warning(f"Skills directory not found: {skills_dir}")
            return []

        discovered = []
        for skill_path in skills_dir.iterdir():
            if not skill_path.is_dir():
                continue

            skill_file = skill_path / "SKILL.md"
            if not skill_file.exists():
                continue

            try:
                metadata = SkillParser.parse_metadata_only(skill_path)
                self.registry.register_skill(metadata, skill_path)
                discovered.append(metadata)
                logger.debug(f"Discovered skill: {metadata.name} from {source_name}")
            except SkillParseError as e:
                logger.warning(f"Failed to parse skill at {skill_path}: {e}")

        return discovered

    def _ensure_github_repo(self, source: SkillSource) -> Path:
        """Ensure GitHub repo is cloned/updated locally."""
        repo_url = f"https://github.com/{source.location}.git"
        return self._ensure_git_repo_from_url(repo_url, source.name, source.branch)

    def _ensure_git_repo(self, source: SkillSource) -> Path:
        """Ensure Git repo is cloned/updated locally."""
        return self._ensure_git_repo_from_url(source.location, source.name, source.branch)

    def _ensure_git_repo_from_url(self, url: str, name: str, branch: str) -> Path:
        """Clone or update a git repository."""
        repo_path = self.cache_path / name

        if repo_path.exists():
            # Update existing repo
            try:
                repo = Repo(repo_path)
                repo.remotes.origin.pull()
                logger.debug(f"Updated repo: {name}")
            except GitCommandError as e:
                logger.warning(f"Failed to update {name}, using cached version: {e}")
        else:
            # Clone new repo (shallow clone for efficiency)
            repo_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                Repo.clone_from(
                    url,
                    repo_path,
                    branch=branch,
                    depth=1,
                )
                logger.info(f"Cloned repo: {name}")
            except GitCommandError as e:
                raise MarketplaceError(f"Failed to clone {url}: {e}")

        return repo_path

    def install(
        self,
        skill_name: str,
        source_name: Optional[str] = None,
        force: bool = False,
    ) -> Path:
        """
        Install a skill to the local skills directory.

        Args:
            skill_name: Name of the skill to install
            source_name: Source to install from (if skill exists in multiple sources)
            force: Overwrite existing installation

        Returns:
            Path to the installed skill
        """
        # Find the skill
        skill_path = self.registry.get_skill_path(skill_name)
        if not skill_path:
            # Try discovering first
            self.discover(source_name)
            skill_path = self.registry.get_skill_path(skill_name)

        if not skill_path:
            raise MarketplaceError(f"Skill not found: {skill_name}")

        # Install to local directory
        dest_path = self.install_path / skill_name

        if dest_path.exists():
            if not force:
                raise MarketplaceError(f"Skill already installed: {skill_name}. Use force=True to overwrite.")
            shutil.rmtree(dest_path)

        # Copy skill folder
        self.install_path.mkdir(parents=True, exist_ok=True)
        shutil.copytree(skill_path, dest_path)

        logger.info(f"Installed skill: {skill_name} to {dest_path}")
        return dest_path

    def uninstall(self, skill_name: str):
        """
        Uninstall a skill from the local skills directory.

        Args:
            skill_name: Name of the skill to uninstall
        """
        skill_path = self.install_path / skill_name

        if not skill_path.exists():
            raise MarketplaceError(f"Skill not installed: {skill_name}")

        shutil.rmtree(skill_path)
        logger.info(f"Uninstalled skill: {skill_name}")

    def list_installed(self) -> List[SkillMetadata]:
        """
        List all installed skills.

        Returns:
            List of installed skill metadata
        """
        if not self.install_path.exists():
            return []

        installed = []
        for skill_path in self.install_path.iterdir():
            if not skill_path.is_dir():
                continue

            try:
                metadata = SkillParser.parse_metadata_only(skill_path)
                installed.append(metadata)
            except SkillParseError:
                logger.warning(f"Invalid skill at {skill_path}")

        return installed

    def get_installed_skill_path(self, skill_name: str) -> Optional[Path]:
        """
        Get the path to an installed skill.

        Args:
            skill_name: Name of the skill

        Returns:
            Path to the skill if installed, None otherwise
        """
        skill_path = self.install_path / skill_name
        if skill_path.exists() and (skill_path / "SKILL.md").exists():
            return skill_path
        return None

    def search(self, query: str) -> List[SkillMetadata]:
        """
        Search for skills by keyword.

        Args:
            query: Search query

        Returns:
            List of matching skills
        """
        return self.registry.search(query)

    def list_sources(self) -> List[SkillSource]:
        """
        List all configured sources.

        Returns:
            List of skill sources
        """
        return list(self.registry.sources.values())
