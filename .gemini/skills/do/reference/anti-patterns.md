# Python Anti-Patterns

## God Class

**WRONG:**
```python
class OrderManager:
    def create_order(self): ...
    def validate_order(self): ...
    def calculate_tax(self): ...
    def apply_discount(self): ...
    def send_email(self): ...
    def generate_pdf(self): ...
    def sync_inventory(self): ...
    def process_payment(self): ...
    # 50 more methods...
```

**RIGHT:** Split into focused classes
```python
class OrderService:
    def create_order(self): ...

class OrderValidator:
    def validate(self): ...

class TaxCalculator:
    def calculate(self): ...

class NotificationService:
    def send_email(self): ...
```

## Boolean Flag Parameters

**WRONG:**
```python
def get_users(include_inactive: bool = False, include_deleted: bool = False):
    ...
```

**RIGHT:** Separate methods or use enum
```python
class UserFilter(Enum):
    ACTIVE = "active"
    ALL = "all"
    DELETED = "deleted"

def get_users(filter: UserFilter = UserFilter.ACTIVE):
    ...
```

## Returning None for Errors

**WRONG:**
```python
def find_user(email: str) -> User | None:
    user = db.query(email)
    return user  # Caller must remember to check None
```

**RIGHT:**
```python
def find_user(email: str) -> User:
    user = db.query(email)
    if not user:
        raise UserNotFoundError(f"No user with email {email}")
    return user
```

## Bare Except

**WRONG:**
```python
try:
    process_data()
except:
    pass  # Swallows ALL errors including KeyboardInterrupt
```

**RIGHT:**
```python
try:
    process_data()
except ValidationError as e:
    logger.warning(f"Validation failed: {e}")
    raise
except DatabaseError as e:
    logger.error(f"Database error: {e}")
    raise ServiceError("Could not process data") from e
```

## Mutable Default Arguments

**WRONG:**
```python
def append_to(item, target=[]):  # Same list reused across calls!
    target.append(item)
    return target
```

**RIGHT:**
```python
def append_to(item, target: list | None = None) -> list:
    if target is None:
        target = []
    target.append(item)
    return target
```

## String Formatting in SQL

**WRONG:**
```python
query = f"SELECT * FROM users WHERE email = '{email}'"  # SQL INJECTION!
```

**RIGHT:**
```python
cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
```

## Scattered Imports

**WRONG:**
```python
def process_data(filepath: str):
    import json  # NEVER import inside functions!
    with open(filepath) as f:
        return json.load(f)

def send_notification():
    from email.mime.text import MIMEText  # NEVER import mid-file!
    ...

def optional_feature():
    try:
        from optional_lib import feature  # NEVER import inside try/except!
    except ImportError:
        feature = None
```

**RIGHT:** All imports at the top of the file
```python
"""Module for data processing and notifications."""
from __future__ import annotations

import json
from email.mime.text import MIMEText
from typing import Any

# Optional dependency handled at module level
try:
    from optional_lib import feature
    HAS_OPTIONAL = True
except ImportError:
    feature = None  # type: ignore
    HAS_OPTIONAL = False


def process_data(filepath: str) -> dict[str, Any]:
    with open(filepath) as f:
        return json.load(f)

def send_notification() -> None:
    ...

def optional_feature() -> None:
    if not HAS_OPTIONAL:
        raise RuntimeError("optional_lib is required for this feature")
    feature()
```

**Why this matters:**
- **Readability**: All dependencies visible at a glance
- **Performance**: Imports inside functions execute every call
- **Debugging**: Easier to spot missing dependencies
- **Tooling**: Linters and import sorters work correctly
