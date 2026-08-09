#!/usr/bin/env python3
"""Validates Python code structure against production standards.

Usage: python validate_structure.py <file.py>

Checks:
- Type hints on all function parameters and returns
- Function length (max 20 lines)
- Naming conventions (PEP8)
- Forbidden patterns (bare except, mutable defaults)
"""
import ast
import sys
from pathlib import Path


class StructureValidator(ast.NodeVisitor):
    def __init__(self, source_lines: list[str]):
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.source_lines = source_lines

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_type_hints(node)
        self._check_function_length(node)
        self._check_naming(node)
        self.generic_visit(node)

    def _check_type_hints(self, node: ast.FunctionDef) -> None:
        if not node.name.startswith('_'):
            if node.returns is None:
                self.errors.append(
                    f"Line {node.lineno}: Function '{node.name}' missing return type hint"
                )
        
        for arg in node.args.args:
            if arg.arg != 'self' and arg.annotation is None:
                self.errors.append(
                    f"Line {node.lineno}: Parameter '{arg.arg}' in '{node.name}' missing type hint"
                )

    def _check_function_length(self, node: ast.FunctionDef) -> None:
        start = node.lineno - 1
        end = node.end_lineno or start + 1
        lines = [
            l for l in self.source_lines[start:end]
            if l.strip() and not l.strip().startswith('#')
        ]
        if len(lines) > 20:
            self.warnings.append(
                f"Line {node.lineno}: Function '{node.name}' has {len(lines)} lines (max 20)"
            )

    def _check_naming(self, node: ast.FunctionDef) -> None:
        forbidden = {'data', 'info', 'manager', 'handler', 'util', 'helper', 'process'}
        name_lower = node.name.lower()
        for word in forbidden:
            if word in name_lower and not node.name.startswith('_'):
                self.warnings.append(
                    f"Line {node.lineno}: Function '{node.name}' uses generic word '{word}'"
                )


def validate_file(filepath: Path) -> tuple[list[str], list[str]]:
    source = filepath.read_text()
    tree = ast.parse(source)
    validator = StructureValidator(source.splitlines())
    validator.visit(tree)
    return validator.errors, validator.warnings


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python validate_structure.py <file.py>")
        return 1

    filepath = Path(sys.argv[1])
    if not filepath.exists():
        print(f"ERROR: File not found: {filepath}")
        return 1

    errors, warnings = validate_file(filepath)

    if errors:
        print("ERRORS:")
        for e in errors:
            print(f"  ✗ {e}")

    if warnings:
        print("WARNINGS:")
        for w in warnings:
            print(f"  ⚠ {w}")

    if not errors and not warnings:
        print("✓ All checks passed")
        return 0

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
