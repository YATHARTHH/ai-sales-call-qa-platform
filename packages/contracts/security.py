"""Security and authorization contracts."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Principal:
    """Authenticated user context consumed by domain authorization rules."""

    user_id: str
    tenant_id: str  # Retailer ID
    roles: list[str] = field(default_factory=list)

    @property
    def is_superadmin(self) -> bool:
        return "superadmin" in self.roles

    def has_role(self, role: str) -> bool:
        return role in self.roles or self.is_superadmin
