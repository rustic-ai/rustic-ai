"""Tests for skills models."""

from rustic_ai.skills.models import (
    SkillAsset,
    SkillDefinition,
    SkillMetadata,
    SkillReference,
    SkillRegistry,
    SkillScript,
    SkillSource,
)


class TestSkillMetadata:
    """Tests for SkillMetadata model."""

    def test_create_basic(self):
        """Test creating basic metadata."""
        metadata = SkillMetadata(
            name="test-skill",
            description="A test skill",
        )
        assert metadata.name == "test-skill"
        assert metadata.description == "A test skill"
        assert metadata.allowed_tools is None
        assert metadata.model is None

    def test_create_with_all_fields(self):
        """Test creating metadata with all fields."""
        metadata = SkillMetadata(
            name="full-skill",
            description="A full skill",
            allowed_tools=["Read", "Write", "Bash"],
            model="gpt-4",
        )
        assert metadata.allowed_tools == ["Read", "Write", "Bash"]
        assert metadata.model == "gpt-4"

    def test_serialization(self):
        """Test metadata serialization."""
        metadata = SkillMetadata(
            name="test",
            description="test description",
            allowed_tools=["Read"],
        )
        data = metadata.model_dump()
        assert data["name"] == "test"
        assert data["allowed_tools"] == ["Read"]


class TestSkillScript:
    """Tests for SkillScript model."""

    def test_create_python_script(self, temp_dir):
        """Test creating a Python script."""
        script_path = temp_dir / "test.py"
        script_path.write_text("print('hello')")

        script = SkillScript(
            name="test",
            path=script_path,
            extension=".py",
            description="Test script",
        )
        assert script.interpreter == "python"

    def test_create_shell_script(self, temp_dir):
        """Test creating a shell script."""
        script = SkillScript(
            name="setup",
            path=temp_dir / "setup.sh",
            extension=".sh",
        )
        assert script.interpreter == "bash"

    def test_interpreter_mapping(self, temp_dir):
        """Test interpreter mapping for different extensions."""
        extensions = {
            ".py": "python",
            ".sh": "bash",
            ".bash": "bash",
            ".js": "node",
            ".ts": "npx ts-node",
            ".rb": "ruby",
            ".unknown": "bash",  # default
        }
        for ext, expected_interpreter in extensions.items():
            script = SkillScript(
                name="test",
                path=temp_dir / f"test{ext}",
                extension=ext,
            )
            assert script.interpreter == expected_interpreter


class TestSkillReference:
    """Tests for SkillReference model."""

    def test_load_reference(self, temp_dir):
        """Test loading reference content."""
        ref_path = temp_dir / "docs.md"
        ref_path.write_text("# Documentation\n\nThis is the docs.")

        ref = SkillReference(name="docs.md", path=ref_path)

        # Content not loaded yet
        assert ref.content is None

        # Load content
        content = ref.load()
        assert content == "# Documentation\n\nThis is the docs."
        assert ref.content == content  # Cached

    def test_load_caches_content(self, temp_dir):
        """Test that load() caches content."""
        ref_path = temp_dir / "test.md"
        ref_path.write_text("original")

        ref = SkillReference(name="test.md", path=ref_path)
        ref.load()

        # Modify file
        ref_path.write_text("modified")

        # Should still return cached content
        assert ref.load() == "original"


class TestSkillDefinition:
    """Tests for SkillDefinition model."""

    def test_convenience_accessors(self, temp_dir):
        """Test name and description accessors."""
        definition = SkillDefinition(
            metadata=SkillMetadata(name="test", description="Test skill"),
            instructions="Do stuff",
            path=temp_dir,
        )
        assert definition.name == "test"
        assert definition.description == "Test skill"

    def test_get_script(self, temp_dir):
        """Test getting script by name."""
        script1 = SkillScript(name="process", path=temp_dir / "process.py", extension=".py")
        script2 = SkillScript(name="setup", path=temp_dir / "setup.sh", extension=".sh")

        definition = SkillDefinition(
            metadata=SkillMetadata(name="test", description="Test"),
            instructions="Instructions",
            path=temp_dir,
            scripts=[script1, script2],
        )

        assert definition.get_script("process") == script1
        assert definition.get_script("setup") == script2
        assert definition.get_script("nonexistent") is None

    def test_get_reference(self, temp_dir):
        """Test getting reference by name."""
        ref = SkillReference(name="docs.md", path=temp_dir / "docs.md")

        definition = SkillDefinition(
            metadata=SkillMetadata(name="test", description="Test"),
            instructions="Instructions",
            path=temp_dir,
            references=[ref],
        )

        assert definition.get_reference("docs.md") == ref
        assert definition.get_reference("nonexistent") is None

    def test_get_asset(self, temp_dir):
        """Test getting asset by name."""
        asset = SkillAsset(name="template.json", path=temp_dir / "template.json")

        definition = SkillDefinition(
            metadata=SkillMetadata(name="test", description="Test"),
            instructions="Instructions",
            path=temp_dir,
            assets=[asset],
        )

        assert definition.get_asset("template.json") == asset
        assert definition.get_asset("nonexistent") is None


class TestSkillSource:
    """Tests for SkillSource model."""

    def test_github_source(self):
        """Test creating a GitHub source."""
        source = SkillSource(
            name="anthropic",
            type="github",
            location="anthropics/skills",
        )
        assert source.branch == "main"  # default
        assert source.skills_path == "skills"  # default

    def test_local_source(self):
        """Test creating a local source."""
        source = SkillSource(
            name="local",
            type="local",
            location="/path/to/skills",
        )
        assert source.type == "local"


class TestSkillRegistry:
    """Tests for SkillRegistry model."""

    def test_add_source(self):
        """Test adding a source."""
        registry = SkillRegistry()
        source = SkillSource(name="test", type="local", location="/tmp")

        registry.add_source(source)
        assert "test" in registry.sources

    def test_register_skill(self, temp_dir):
        """Test registering a skill."""
        registry = SkillRegistry()
        metadata = SkillMetadata(name="test-skill", description="Test")

        registry.register_skill(metadata, temp_dir)

        assert "test-skill" in registry.skills
        assert registry.get_skill_path("test-skill") == temp_dir

    def test_list_skills(self, temp_dir):
        """Test listing skills."""
        registry = SkillRegistry()
        metadata1 = SkillMetadata(name="skill1", description="First")
        metadata2 = SkillMetadata(name="skill2", description="Second")

        registry.register_skill(metadata1, temp_dir / "skill1")
        registry.register_skill(metadata2, temp_dir / "skill2")

        skills = registry.list_skills()
        assert len(skills) == 2

    def test_search(self, temp_dir):
        """Test searching skills."""
        registry = SkillRegistry()
        registry.register_skill(SkillMetadata(name="pdf-reader", description="Read PDF files"), temp_dir / "pdf")
        registry.register_skill(SkillMetadata(name="csv-parser", description="Parse CSV data"), temp_dir / "csv")
        registry.register_skill(
            SkillMetadata(name="web-search", description="Search the web for information"), temp_dir / "web"
        )

        # Search by name
        results = registry.search("pdf")
        assert len(results) == 1
        assert results[0].name == "pdf-reader"

        # Search by description
        results = registry.search("search")
        assert len(results) == 1
        assert results[0].name == "web-search"

        # Case insensitive
        results = registry.search("CSV")
        assert len(results) == 1
