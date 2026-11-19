from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class Rule(_Base):
    action: str
    resource: str
    effect: Literal["allow", "deny", "ask"]


class ModelRef(_Base):
    id: str
    provider_id: str = Field(alias="providerID")
    variant: str = "default"


class SessionTime(_Base):
    created: int = 0
    updated: int = 0
    busy: int | None = None
    idle: int | None = None

    def is_busy(self) -> bool:
        return (self.busy or 0) > (self.idle or 0)


class Location(_Base):
    directory: str


class SessionInfo(_Base):
    id: str
    parent_id: str | None = Field(default=None, alias="parentID")
    title: str = ""
    agent: str | None = None
    model: ModelRef | None = None
    project_id: str | None = Field(default=None, alias="projectID")
    cost: float = 0.0
    outcome: str | None = None
    time: SessionTime = Field(default_factory=SessionTime)
    permissions: list[Rule] = []
    location: Location | None = None

    @property
    def directory(self) -> str | None:
        return self.location.directory if self.location else None


class ProjectTime(_Base):
    created: int = 0
    updated: int = 0
    active: int = 0


class Project(_Base):
    id: str
    canonical: str
    name: str | None = None
    time: ProjectTime = Field(default_factory=ProjectTime)

    @property
    def title(self) -> str:
        return self.name or self.canonical.rsplit("/", 1)[-1] or self.canonical


class ModelInfo(_Base):
    id: str
    model_id: str = Field(alias="modelID")
    provider_id: str = Field(alias="providerID")
    name: str = ""
    enabled: bool = True
    variants: list[dict[str, Any]] = []

    @property
    def label(self) -> str:
        return self.name or self.model_id


class AgentInfo(_Base):
    id: str
    name: str = ""
    mode: str | None = None
    hidden: bool = False

    @property
    def label(self) -> str:
        return self.name or self.id


class PermissionSource(_Base):
    type: str | None = None
    directory: str | None = None


class PermissionRequest(_Base):
    id: str
    session_id: str = Field(alias="sessionID")
    action: str
    resources: list[str] = []
    source: PermissionSource | None = None
    message: str | None = None
    save: list[str] = []
