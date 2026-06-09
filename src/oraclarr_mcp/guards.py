from dataclasses import dataclass
from .models import Risk


@dataclass(frozen=True)
class ToolSpec:
    name: str
    risk: Risk
    domain: str  # toolset name, or "always"


class WriteNotAllowed(Exception):
    pass


def tool_spec(name: str, risk: Risk, domain: str) -> ToolSpec:
    return ToolSpec(name=name, risk=risk, domain=domain)


def enabled_for_toolsets(specs: list[ToolSpec], toolsets: list[str]) -> list[str]:
    return [s.name for s in specs if s.domain == "always" or s.domain in toolsets]


def ensure_allowed(spec: ToolSpec, allow_writes: bool) -> None:
    if spec.risk != "read" and not allow_writes:
        raise WriteNotAllowed(f"Tool {spec.name} is {spec.risk}; allow_writes is false")
