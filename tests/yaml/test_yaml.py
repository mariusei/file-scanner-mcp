"""Tests for YAML language."""

from pathlib import Path

import pytest

from scantool.languages.yaml import YAMLLanguage


@pytest.fixture
def yaml_language():
    """Create YAML language instance."""
    return YAMLLanguage()


@pytest.fixture
def basic_yaml():
    """Load basic.yaml test file."""
    path = Path(__file__).parent / "samples" / "basic.yaml"
    return path.read_bytes()


@pytest.fixture
def broken_yaml():
    """Load broken.yaml test file."""
    path = Path(__file__).parent / "samples" / "broken.yaml"
    return path.read_bytes()


@pytest.fixture
def comments_yaml():
    """Load comments.yaml: a header block, attached doc lines, mid-file
    blocks, a trailing comment and a comment inside a sequence."""
    path = Path(__file__).parent / "samples" / "comments.yaml"
    return path.read_bytes()


class TestYAMLScanner:
    """Tests for YAMLLanguage structure extraction."""

    def test_get_extensions(self):
        extensions = YAMLLanguage.get_extensions()
        assert ".yaml" in extensions
        assert ".yml" in extensions

    def test_get_language_name(self):
        assert YAMLLanguage.get_language_name() == "YAML"

    def test_should_skip_lock_file(self):
        assert YAMLLanguage.should_skip("pnpm-lock.yaml") is True
        assert YAMLLanguage.should_skip("app.yaml") is False

    def test_should_skip_minified(self):
        assert YAMLLanguage.should_skip("config.min.yaml") is True

    def test_registry_prefers_yaml_language_over_config(self):
        """The registry must route .yaml/.yml to YAMLLanguage, not ConfigLanguage."""
        from scantool.languages import get_language
        from scantool.languages.config import ConfigLanguage

        assert isinstance(get_language(".yaml"), YAMLLanguage)
        assert isinstance(get_language(".yml"), YAMLLanguage)
        assert not isinstance(get_language(".yaml"), ConfigLanguage)

    def test_scan_top_level_keys(self, yaml_language, basic_yaml):
        """Top-level keys become nodes; the file has two documents."""
        structures = yaml_language.scan(basic_yaml)
        assert structures is not None

        docs = [s for s in structures if s.type == "document"]
        assert len(docs) == 2
        assert docs[0].synthetic is True
        assert docs[1].synthetic is True

        top_keys = {c.name for c in docs[0].children}
        assert {"name", "shared_timeout", "on", "jobs", "notes"} <= top_keys

    def test_scan_scalar_signature(self, yaml_language, basic_yaml):
        structures = yaml_language.scan(basic_yaml)
        doc1 = [s for s in structures if s.type == "document"][0]
        name_node = next(c for c in doc1.children if c.name == "name")
        assert name_node.type == "scalar"
        assert name_node.signature == "sample-workflow"
        assert name_node.synthetic is False

    def test_scan_anchor_and_alias(self, yaml_language, basic_yaml):
        structures = yaml_language.scan(basic_yaml)
        doc1 = [s for s in structures if s.type == "document"][0]
        timeout_node = next(c for c in doc1.children if c.name == "shared_timeout")
        assert any(m.startswith("anchor:timeout") for m in timeout_node.modifiers)

        jobs_node = next(c for c in doc1.children if c.name == "jobs")
        build_node = next(c for c in jobs_node.children if c.name == "build")
        alias_node = next(c for c in build_node.children if c.name == "timeout-minutes")
        assert alias_node.signature == "*timeout"
        assert "alias" in alias_node.modifiers

    def test_scan_sequence_signature(self, yaml_language, basic_yaml):
        structures = yaml_language.scan(basic_yaml)
        doc1 = [s for s in structures if s.type == "document"][0]
        on_node = next(c for c in doc1.children if c.name == "on")
        push_node = next(c for c in on_node.children if c.name == "push")
        branches_node = next(c for c in push_node.children if c.name == "branches")
        assert branches_node.type == "sequence"
        assert branches_node.signature == "[2] main, develop"

    def test_scan_jobs_have_needs_runs_on_steps(self, yaml_language, basic_yaml):
        """jobs.<id> exposes needs, runs-on and steps[].name as children."""
        structures = yaml_language.scan(basic_yaml)
        doc1 = [s for s in structures if s.type == "document"][0]
        jobs_node = next(c for c in doc1.children if c.name == "jobs")
        test_job = next(c for c in jobs_node.children if c.name == "test")

        needs_node = next(c for c in test_job.children if c.name == "needs")
        assert needs_node.type == "sequence"
        assert needs_node.signature == "[1] build"

        runs_on_node = next(c for c in test_job.children if c.name == "runs-on")
        assert runs_on_node.type == "scalar"
        assert runs_on_node.signature == "ubuntu-latest"

        steps_node = next(c for c in test_job.children if c.name == "steps")
        assert steps_node.type == "sequence"
        step_names = [c.name for c in steps_node.children]
        assert step_names == ["Checkout", "Run tests"]
        # The "name" key that produced the label is not repeated as a child.
        checkout_step = steps_node.children[0]
        assert all(c.name != "name" for c in checkout_step.children)
        assert checkout_step.synthetic is False

    def test_scan_block_scalar(self, yaml_language, basic_yaml):
        structures = yaml_language.scan(basic_yaml)
        doc1 = [s for s in structures if s.type == "document"][0]
        notes_node = next(c for c in doc1.children if c.name == "notes")
        assert notes_node.type == "scalar"
        assert "folded" in notes_node.modifiers

        jobs_node = next(c for c in doc1.children if c.name == "jobs")
        test_job = next(c for c in jobs_node.children if c.name == "test")
        steps_node = next(c for c in test_job.children if c.name == "steps")
        run_step = steps_node.children[1]
        run_node = next(c for c in run_step.children if c.name == "run")
        assert "literal" in run_node.modifiers

    def test_scan_second_document(self, yaml_language, basic_yaml):
        structures = yaml_language.scan(basic_yaml)
        doc2 = [s for s in structures if s.type == "document"][1]
        service_node = next(c for c in doc2.children if c.name == "service")
        tags_node = next(c for c in service_node.children if c.name == "tags")
        assert tags_node.signature == "[2] prod, critical"

    def test_scan_broken_yaml_does_not_crash(self, yaml_language, broken_yaml):
        structures = yaml_language.scan(broken_yaml)
        assert structures is not None


class TestYAMLCommentBlocks:
    """Full-line comments are structure: blocks become `comment` nodes,
    an attached single line becomes the key's docstring."""

    def test_leading_header_separated_by_a_blank_line_is_a_comment_node(
        self, yaml_language, comments_yaml
    ):
        structures = yaml_language.scan(comments_yaml)
        header = structures[0]
        assert header.type == "comment"
        assert (header.start_line, header.end_line) == (1, 8)
        # Named by the first line of prose, not the banner on line 1
        assert header.name == "Runtime table for the launcher"
        assert header.signature == "8 lines"

    def test_synthetic_follows_whether_the_name_is_on_the_first_line(
        self, yaml_language, comments_yaml
    ):
        structures = yaml_language.scan(comments_yaml)
        header, trailing = structures[0], structures[-1]
        assert header.synthetic is True  # named from line 2, a banner is line 1
        assert trailing.type == "comment"
        assert trailing.start_line == trailing.end_line == 28
        assert trailing.name.startswith("Trailing note after the last key")
        assert trailing.synthetic is False  # its name is the first line itself

    def test_attached_single_line_becomes_the_docstring(self, yaml_language, comments_yaml):
        structures = yaml_language.scan(comments_yaml)
        promoted = next(s for s in structures if s.name == "promoted")
        assert promoted.docstring == "The version new installs get"
        assert promoted.signature == "0.2.0"  # the trailing comment is left alone
        default = next(s for s in structures if s.name == "default")
        assert default.docstring is None

    def test_mid_file_block_sits_before_the_key_that_follows_it(self, yaml_language, comments_yaml):
        structures = yaml_language.scan(comments_yaml)
        names = [s.name for s in structures]
        block = next(s for s in structures if s.type == "comment" and s.start_line == 13)
        assert block.end_line == 15
        assert block.name == "Kept for one release so old installs can roll back"
        assert names.index(block.name) == names.index("versions") - 1
        # A multi-line block directly above a key is a node, not a docstring
        assert next(s for s in structures if s.name == "versions").docstring is None

    def test_comments_inside_sequences(self, yaml_language, comments_yaml):
        structures = yaml_language.scan(comments_yaml)
        versions = next(s for s in structures if s.name == "versions")
        # Above a scalar item there is nothing to attach to: an ordinary block
        assert [c.type for c in versions.children] == ["comment"]
        assert versions.signature == "[2] 0.2.0, 0.1.2"
        steps = next(s for s in structures if s.name == "steps")
        checkout = next(c for c in steps.children if c.name == "Checkout")
        assert checkout.docstring.startswith("Checkout must run first")
        assert steps.signature == "2 items"

    def test_short_lone_line_is_dropped(self, yaml_language, comments_yaml):
        structures = yaml_language.scan(comments_yaml)
        assert not any(s.name == "TODO" for s in structures)
        tags = next(s for s in structures if s.name == "tags")
        assert tags.docstring == "TODO"  # attached, so it documents the key

    def test_comment_only_file(self, yaml_language):
        structures = yaml_language.scan(b"# Placeholder: filled in by the generator\n")
        assert [(s.type, s.start_line) for s in structures] == [("comment", 1)]

    def test_no_comments_no_change(self, yaml_language):
        structures = yaml_language.scan(b"name: worker\nservice:\n  replicas: 3\n")
        assert not any(s.type == "comment" for s in structures)
        assert all(s.docstring is None for s in structures)


class TestYAMLAnalyzer:
    """Tests for YAMLLanguage semantic analysis (moved from ConfigLanguage)."""

    def test_should_analyze_skip_lock_files(self, yaml_language):
        assert yaml_language.should_analyze("pnpm-lock.yaml") is False

    def test_should_analyze_normal_files(self, yaml_language):
        assert yaml_language.should_analyze("docker-compose.yml") is True

    def test_extract_imports_docker_compose_env_file(self, yaml_language):
        content = """version: '3'
services:
  web:
    env_file: .env.production
    image: nginx
"""
        imports = yaml_language.extract_imports("docker-compose.yml", content)
        env_imports = [imp for imp in imports if imp.import_type == "env_file"]
        assert len(env_imports) == 1
        assert env_imports[0].target_module == ".env.production"

    def test_extract_imports_docker_compose_dockerfile(self, yaml_language):
        content = """version: '3'
services:
  app:
    build:
      dockerfile: ./docker/Dockerfile.prod
"""
        imports = yaml_language.extract_imports("docker-compose.yml", content)
        dockerfile_imports = [imp for imp in imports if imp.import_type == "dockerfile"]
        assert len(dockerfile_imports) == 1
        assert dockerfile_imports[0].target_module == "./docker/Dockerfile.prod"

    def test_extract_imports_docker_compose_volumes(self, yaml_language):
        content = """version: '3'
services:
  db:
    volumes:
      - ./data:/var/lib/postgresql/data
      - ./config:/etc/config
"""
        imports = yaml_language.extract_imports("docker-compose.yml", content)
        volume_imports = [imp for imp in imports if imp.import_type == "volume_mount"]
        assert len(volume_imports) >= 2
        assert any(imp.target_module == "./data" for imp in volume_imports)
        assert any(imp.target_module == "./config" for imp in volume_imports)

    def test_extract_imports_multiline_yaml(self, yaml_language):
        content = """version: '3'
services:
  web:
    volumes:
      - ./app:/app
      - ./config:/config
    env_file:
      - .env
      - .env.local
"""
        imports = yaml_language.extract_imports("docker-compose.yml", content)
        volume_imports = [imp for imp in imports if imp.import_type == "volume_mount"]
        assert len(volume_imports) >= 2

    def test_extract_imports_generic_quoted_paths(self, yaml_language):
        content = """
template: "./templates/base.html"
stylesheet: "../assets/style.css"
"""
        imports = yaml_language.extract_imports("custom.yaml", content)
        assert any(imp.target_module == "./templates/base.html" for imp in imports)
        assert any(imp.target_module == "../assets/style.css" for imp in imports)

    def test_extract_imports_no_urls(self, yaml_language):
        content = """
api: "https://api.example.com/data.yaml"
local: "./local/file.yaml"
"""
        imports = yaml_language.extract_imports("config.yaml", content)
        assert any(imp.target_module == "./local/file.yaml" for imp in imports)
        assert not any("https://" in imp.target_module for imp in imports)

    def test_extract_imports_empty_file(self, yaml_language):
        assert yaml_language.extract_imports("empty.yaml", "") == []

    def test_find_entry_points_docker_compose(self, yaml_language):
        content = """version: '3'
services:
  web:
    image: nginx
"""
        entry_points = yaml_language.find_entry_points("docker-compose.yml", content)
        project_entries = [ep for ep in entry_points if ep.type == "project_config"]
        assert len(project_entries) == 1
        assert project_entries[0].framework == "Docker"

    def test_find_entry_points_docker_compose_services(self, yaml_language):
        content = """version: '3'
services:
  web:
    image: nginx
  db:
    image: postgres
"""
        entry_points = yaml_language.find_entry_points("docker-compose.yml", content)
        service_entries = [ep for ep in entry_points if ep.type == "services_section"]
        assert len(service_entries) == 1

    def test_find_entry_points_empty_file(self, yaml_language):
        assert yaml_language.find_entry_points("empty.yaml", "") == []

    def test_classify_file_config(self, yaml_language):
        assert yaml_language.classify_file("docker-compose.yml", "") == "config"

    def test_resolve_import_to_file_relative(self, yaml_language):
        result = yaml_language.resolve_import_to_file(
            "config.yaml", "docker/docker-compose.yml", ["docker/config.yaml"], {}
        )
        assert result == "docker/config.yaml"

    def test_resolve_import_to_file_direct_match(self, yaml_language):
        result = yaml_language.resolve_import_to_file(
            "config.yaml", "docker-compose.yml", ["config.yaml"], {}
        )
        assert result == "config.yaml"
