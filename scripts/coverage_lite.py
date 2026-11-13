"""Approximate LINE coverage using sys.settrace. Not coverage.py; no branch coverage.

Executable lines are taken from the AST (statement start lines). A statement counts as covered
if the tracer saw its first line execute. Output: per-file table and reports/coverage.xml
(Cobertura-style, line-rate only).
"""

from __future__ import annotations

import ast
import os
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "bangzen_prime")


def executable_lines(path: str) -> set[int]:
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=path)
    lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.stmt) and not isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            lines.add(node.lineno)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            lines.add(node.lineno)
    # Docstrings are statements too, but they are never "executed" meaningfully: drop them.
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            if (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(getattr(node.body[0], "value", None), ast.Constant)
            ):
                lines.discard(node.body[0].lineno)
    return lines


def main() -> int:
    sys.path.insert(0, ROOT)
    os.chdir(ROOT)
    hits: dict[str, set[int]] = {}

    def tracer(frame, event, arg):
        filename = frame.f_code.co_filename
        if not filename.startswith(PKG):
            return None
        bucket = hits.setdefault(filename, set())

        def local(frame, event, arg):
            if event == "line":
                bucket.add(frame.f_lineno)
            return local

        if event == "call":
            bucket.add(frame.f_lineno)
        return local

    # Tracer must be installed BEFORE discovery imports the package, so module-level
    # statements (imports, constants, class bodies) are counted as executed.
    sys.settrace(tracer)
    try:
        suite = unittest.TestLoader().discover(
            os.path.join(ROOT, "tests"), top_level_dir=ROOT, pattern="test_*.py"
        )
        result = unittest.TextTestRunner(stream=open(os.devnull, "w"), verbosity=0).run(
            suite
        )
    finally:
        sys.settrace(None)

    total_exec = total_hit = 0
    rows = []
    for dirpath, _, files in os.walk(PKG):
        for name in sorted(files):
            if not name.endswith(".py"):
                continue
            path = os.path.join(dirpath, name)
            exe = executable_lines(path)
            covered = exe & hits.get(path, set())
            total_exec += len(exe)
            total_hit += len(covered)
            pct = 100.0 * len(covered) / len(exe) if exe else 100.0
            rows.append((os.path.relpath(path, ROOT), len(exe), len(covered), pct))
    rows.sort()
    print(f"{'file':60} {'stmts':>6} {'hit':>6} {'pct':>7}")
    for rel, n, h, p in rows:
        print(f"{rel:60} {n:6d} {h:6d} {p:6.1f}%")
    overall = 100.0 * total_hit / total_exec if total_exec else 0.0
    print(
        f"TOTAL statements={total_exec} hit={total_hit} line_coverage={overall:.2f}% "
        f"(approximate, stdlib tracer; branch coverage not measured)"
    )
    print(
        f"tests_run={result.testsRun} failures={len(result.failures)} errors={len(result.errors)}"
    )

    root = ET.Element(
        "coverage",
        **{
            "line-rate": f"{overall / 100:.4f}",
            "branch-rate": "0",
            "lines-valid": str(total_exec),
            "lines-covered": str(total_hit),
            "version": "stdlib-tracer-approx",
        },
    )
    packages = ET.SubElement(root, "packages")
    pkg = ET.SubElement(packages, "package", name="bangzen_prime")
    classes = ET.SubElement(pkg, "classes")
    for rel, n, h, p in rows:
        ET.SubElement(
            classes,
            "class",
            filename=rel,
            name=os.path.basename(rel),
            **{"line-rate": f"{p / 100:.4f}", "branch-rate": "0"},
        )
    os.makedirs(os.path.join(ROOT, "reports"), exist_ok=True)
    ET.ElementTree(root).write(
        os.path.join(ROOT, "reports", "coverage.xml"),
        encoding="utf-8",
        xml_declaration=True,
    )
    return 0 if not result.failures and not result.errors else 1


if __name__ == "__main__":
    sys.exit(main())
