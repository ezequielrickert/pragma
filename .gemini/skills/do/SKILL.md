---
name: generating-python-code
description: Generates production-ready Python code following PEP standards, type hints, and clean code principles. Use when user requests Python implementation of classes, functions, services, or modules. Triggers on "implement", "write", "Python code", "create class", "create function", "code for".
allowed-tools: Read, Write, Edit, Bash(python:*)
---

# Generating Python Code

## Workflow

```
1. CHECK PREREQUISITES → Verify design exists if Medium+
2. APPLY STANDARDS → Type hints, docstrings, naming
3. IMPLEMENT → Write code following patterns
4. VALIDATE → Run validate_structure.py
5. SECURE → Use securing-code skill before delivery
```

## Pre-Generation Checklist

Before writing code:

- [ ] Design exists or complexity is Trivial/Low
- [ ] I know WHAT to build (not just HOW)
- [ ] Dependencies are clear

If complexity is Medium+, use `designing-systems` skill first.

## Mandatory Code Standards

### Import Organization (PEP 8)

**ALL imports MUST be at the top of the file**, after the module docstring and before any other code.

```python
# RIGHT - Imports at the top, organized
"""Module docstring."""
from __future__ import annotations

import os
import sys
from typing import Protocol

from third_party import SomeClass

from myproject.domain import Entity


def my_function():
    ...
```

```python
# WRONG - Imports scattered in code
def process_data():
    import json  # NEVER import inside functions
    ...

def another_function():
    try:
        from module import thing  # NEVER import inside try/except
    except ImportError:
        thing = None
```

**Import order (isort standard):**

1. `__future__` imports
2. Standard library imports
3. Third-party imports
4. Local application imports

Each group separated by a blank line.

### Type Hints (ALWAYS)

```python
# WRONG
def process(data):
    return data.upper()

# RIGHT
def process(data: str) -> str:
    return data.upper()
```

### Docstrings (Public APIs)

```python
def calculate_total(items: list[LineItem], tax_rate: Decimal) -> Money:
    """Calculate order total including tax.

    Args:
        items: Line items with price and quantity
        tax_rate: Tax rate as decimal (0.21 for 21%)

    Returns:
        Total amount as Money value object

    Raises:
        InvalidTaxRateError: If tax_rate is negative
    """
```

### Naming Conventions

| Element   | Convention            | Example           |
| --------- | --------------------- | ----------------- |
| Classes   | PascalCase, noun      | `OrderProcessor`  |
| Functions | snake_case, verb+noun | `calculate_total` |
| Constants | UPPER_SNAKE           | `MAX_RETRIES`     |
| Private   | \_prefix              | `_validate_input` |

### Forbidden Names

`data`, `info`, `manager`, `handler`, `util`, `helper`, `misc`, `process` (too generic)

## Error Handling Pattern

```python
# WRONG - Silent failure
def get_user(user_id: str) -> User | None:
    user = db.find(user_id)
    return user  # Caller might forget to check None

# RIGHT - Explicit failure
def get_user(user_id: str) -> User:
    user = db.find(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")
    return user
```

## Function Rules

- **Max 20 lines** (ideal: 5-10)
- **Max 3 parameters** (use dataclass/TypedDict for more)
- **No boolean flags** as parameters
- **Single responsibility**

## Prohibited Patterns

| Pattern                         | Why Bad                     | Fix                       |
| ------------------------------- | --------------------------- | ------------------------- |
| `except Exception`              | Swallows all errors         | Catch specific exceptions |
| `return None` for errors        | Caller forgets to check     | Raise domain exception    |
| `if isinstance(x, Type)` chains | Type-based branching        | Use polymorphism          |
| Global mutable state            | Untestable, race conditions | Inject dependencies       |
| String concatenation for SQL    | SQL injection               | Use parameterized queries |
| Hard-coded config values        | Inflexible                  | Use environment/config    |

## Validation Script

After generating code, validate structure:

```bash
python scripts/validate_structure.py generated_file.py
```

This checks: type hints present, function length, naming conventions.

## Examples

For complete input/output examples → See [reference/examples.md](reference/examples.md)
For what NOT to do → See [reference/anti-patterns.md](reference/anti-patterns.md)

## Output Format

```python
"""
Module docstring explaining purpose.
"""
from __future__ import annotations

from typing import Protocol
from dataclasses import dataclass

# Interfaces first
class IRepository(Protocol):
    ...

# Value Objects
@dataclass(frozen=True)
class Money:
    ...

# Domain classes
class Service:
    ...
```

## After Generation

- Run `validate_structure.py` to check standards
- Use `securing-code` skill before delivery
