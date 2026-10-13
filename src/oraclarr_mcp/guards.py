from dataclasses import dataclass
from .models import Risk


@dataclass(frozen=True)
class ToolSpec:
    name: str
    risk: Risk
    domain: str  # toolset name, or "always"


def tool_spec(name: str, risk: Risk, domain: str) -> ToolSpec:
    return ToolSpec(name=name, risk=risk, domain=domain)


def enabled_for_toolsets(specs: list[ToolSpec], toolsets: list[str]) -> list[str]:
    return [s.name for s in specs if s.domain == "always" or s.domain in toolsets]


def writable_instances(cfg) -> set[str]:
    """Instances a write may reach: server switch on and the instance opted in."""
    if not cfg.server.allow_writes:
        return set()
    return {n for n, i in cfg.instances.items() if i.enabled and i.allow_writes}
