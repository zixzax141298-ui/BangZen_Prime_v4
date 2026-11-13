"""Minimal unused-import check (AST based). Substitute for ruff F401, which is not installable here."""

import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGETS = ["bangzen_prime", "tests", "scripts"]


def check(path: str) -> list[str]:
    with open(path, encoding="utf-8") as fh:
        source = fh.read()
    tree = ast.parse(source, filename=path)
    imported: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported[(alias.asname or alias.name).split(".")[0]] = node.lineno
        elif isinstance(node, ast.ImportFrom):
            if node.module == "__future__":
                continue
            for alias in node.names:
                imported[alias.asname or alias.name] = node.lineno
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    used |= {n.value.id for n in ast.walk(tree) if isinstance(n, ast.Attribute)
             and isinstance(n.value, ast.Name)}
    exported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__all__"
                                                for t in node.targets):
            exported |= {elt.value for elt in node.value.elts if isinstance(elt, ast.Constant)}
    issues = []
    for name, line in imported.items():
        if name not in used and name not in exported and not source.count(name) > 1:
            issues.append(f"{os.path.relpath(path, ROOT)}:{line}: unused import {name}")
    return issues


def main() -> int:
    issues: list[str] = []
    for target in TARGETS:
        for dirpath, _, files in os.walk(os.path.join(ROOT, target)):
            for name in files:
                if name.endswith(".py"):
                    issues.extend(check(os.path.join(dirpath, name)))
    print("\n".join(issues) if issues else "no unused imports found")
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
