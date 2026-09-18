"""Architectural boundary enforcement tests using AST inspection."""

import ast
from pathlib import Path


def get_imported_modules(file_path: Path) -> set[str]:
    """Parse python source and extract top-level imported package names."""
    with open(file_path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=str(file_path))

    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    return imports


def test_domain_layer_has_zero_infrastructure_dependencies():
    """Domain layer must not import infrastructure, API, or third-party frameworks."""
    forbidden = {
        "fastapi",
        "sqlalchemy",
        "redis",
        "boto3",
        "botocore",
        "openai",
        "anthropic",
        "infrastructure",
        "apps",
    }

    domain_dir = Path("packages/domain")
    assert domain_dir.exists()

    for py_file in domain_dir.glob("*.py"):
        imports = get_imported_modules(py_file)
        violations = imports.intersection(forbidden)
        assert not violations, (
            f"Architectural boundary violation in {py_file}: "
            f"Domain must not import {violations}"
        )


def test_evaluation_layer_has_zero_infrastructure_dependencies():
    """Evaluation contracts must not import database, API, or cloud infrastructure."""
    forbidden = {
        "fastapi",
        "sqlalchemy",
        "redis",
        "boto3",
        "botocore",
        "infrastructure",
        "apps",
    }

    eval_dir = Path("packages/evaluation")
    assert eval_dir.exists()

    for py_file in eval_dir.glob("*.py"):
        imports = get_imported_modules(py_file)
        violations = imports.intersection(forbidden)
        assert not violations, (
            f"Architectural boundary violation in {py_file}: "
            f"Evaluation must not import {violations}"
        )


def test_application_layer_does_not_import_infrastructure_directly():
    """Application layer defines ports and must not import concrete infrastructure."""
    forbidden = {
        "packages.infrastructure",
        "apps",
    }

    app_dir = Path("packages/application")
    assert app_dir.exists()

    for py_file in app_dir.rglob("*.py"):
        with open(py_file, encoding="utf-8") as f:
            content = f.read()
            for f_import in forbidden:
                assert f"from {f_import}" not in content, (
                    f"Application layer violation in {py_file}: imports {f_import}"
                )
