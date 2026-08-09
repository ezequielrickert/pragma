# Python Code Examples

## Example 1: Repository Pattern

**Input**: "Create a user repository with CRUD operations"

**Output**:

```python
"""User repository with database abstraction."""
from __future__ import annotations

from typing import Protocol
from dataclasses import dataclass
from uuid import UUID


class UserNotFoundError(Exception):
    """Raised when user does not exist."""


@dataclass(frozen=True)
class User:
    id: UUID
    email: str
    name: str


class IUserRepository(Protocol):
    """Repository interface for User aggregate."""
    
    def get(self, user_id: UUID) -> User:
        """Get user by ID. Raises UserNotFoundError if not found."""
        ...
    
    def save(self, user: User) -> None:
        """Persist user to storage."""
        ...
    
    def delete(self, user_id: UUID) -> None:
        """Remove user. Raises UserNotFoundError if not found."""
        ...


class PostgresUserRepository:
    """PostgreSQL implementation of user repository."""
    
    def __init__(self, connection_pool: ConnectionPool) -> None:
        self._pool = connection_pool
    
    def get(self, user_id: UUID) -> User:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT id, email, name FROM users WHERE id = %s",
                (str(user_id),)
            ).fetchone()
        
        if not row:
            raise UserNotFoundError(f"User {user_id} not found")
        
        return User(id=row[0], email=row[1], name=row[2])
    
    def save(self, user: User) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO users (id, email, name) 
                VALUES (%s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET email = %s, name = %s
                """,
                (str(user.id), user.email, user.name, user.email, user.name)
            )
    
    def delete(self, user_id: UUID) -> None:
        with self._pool.connection() as conn:
            result = conn.execute(
                "DELETE FROM users WHERE id = %s",
                (str(user_id),)
            )
        
        if result.rowcount == 0:
            raise UserNotFoundError(f"User {user_id} not found")
```

## Example 2: Strategy Pattern

**Input**: "Create a payment processor that supports multiple providers"

**Output**:

```python
"""Payment processing with pluggable providers."""
from __future__ import annotations

from typing import Protocol
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class PaymentStatus(Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class PaymentResult:
    status: PaymentStatus
    transaction_id: str
    message: str


class IPaymentProvider(Protocol):
    """Payment provider interface."""
    
    def charge(self, amount: Decimal, currency: str, token: str) -> PaymentResult:
        """Process payment. Returns result with status."""
        ...


class StripeProvider:
    """Stripe payment implementation."""
    
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
    
    def charge(self, amount: Decimal, currency: str, token: str) -> PaymentResult:
        # Stripe-specific implementation
        ...


class PaymentService:
    """Orchestrates payment processing."""
    
    def __init__(self, provider: IPaymentProvider) -> None:
        self._provider = provider
    
    def process_payment(
        self, 
        amount: Decimal, 
        currency: str, 
        token: str
    ) -> PaymentResult:
        if amount <= 0:
            raise ValueError("Amount must be positive")
        
        return self._provider.charge(amount, currency, token)
```

## Example 3: Service with Dependency Injection

**Input**: "Create an order service that validates and persists orders"

**Output**:

```python
"""Order service with validation and persistence."""
from __future__ import annotations

from typing import Protocol
from dataclasses import dataclass
from uuid import UUID, uuid4
from decimal import Decimal


class OrderValidationError(Exception):
    """Raised when order validation fails."""


@dataclass(frozen=True)
class OrderLine:
    product_id: UUID
    quantity: int
    unit_price: Decimal


@dataclass
class Order:
    id: UUID
    customer_id: UUID
    lines: list[OrderLine]
    
    @property
    def total(self) -> Decimal:
        return sum(line.quantity * line.unit_price for line in self.lines)


class IOrderRepository(Protocol):
    def save(self, order: Order) -> None: ...
    def get(self, order_id: UUID) -> Order: ...


class IInventoryService(Protocol):
    def check_availability(self, product_id: UUID, quantity: int) -> bool: ...


class OrderService:
    """Creates and manages orders."""
    
    def __init__(
        self,
        repository: IOrderRepository,
        inventory: IInventoryService,
    ) -> None:
        self._repository = repository
        self._inventory = inventory
    
    def create_order(
        self,
        customer_id: UUID,
        lines: list[OrderLine],
    ) -> Order:
        self._validate_lines(lines)
        
        order = Order(
            id=uuid4(),
            customer_id=customer_id,
            lines=lines,
        )
        
        self._repository.save(order)
        return order
    
    def _validate_lines(self, lines: list[OrderLine]) -> None:
        if not lines:
            raise OrderValidationError("Order must have at least one line")
        
        for line in lines:
            if not self._inventory.check_availability(line.product_id, line.quantity):
                raise OrderValidationError(
                    f"Product {line.product_id} not available in quantity {line.quantity}"
                )
```
