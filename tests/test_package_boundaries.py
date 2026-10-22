"""Architecture guard: production code never depends on the command-line tools."""

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PRODUCTION_PACKAGES = ("jose_wipes", "webapp")
TOOLS_PACKAGE = "scripts"


def _imported_modules(source_path: Path) -> set[str]:
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)
    return modules


def _depends_on_tools(module: str) -> bool:
    return module == TOOLS_PACKAGE or module.startswith(f"{TOOLS_PACKAGE}.")


def test_production_packages_do_not_import_scripts():
    violations = [
        f"{source_path.relative_to(PROJECT_ROOT).as_posix()} -> {module}"
        for package in PRODUCTION_PACKAGES
        for source_path in sorted((PROJECT_ROOT / package).rglob("*.py"))
        for module in sorted(_imported_modules(source_path))
        if _depends_on_tools(module)
    ]

    assert violations == []


def test_domain_package_does_not_import_web_layer():
    violations = [
        f"{source_path.relative_to(PROJECT_ROOT).as_posix()} -> {module}"
        for source_path in sorted((PROJECT_ROOT / "jose_wipes").rglob("*.py"))
        for module in sorted(_imported_modules(source_path))
        if module == "webapp" or module.startswith("webapp.")
    ]

    assert violations == []
