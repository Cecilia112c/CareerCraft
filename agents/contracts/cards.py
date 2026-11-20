from pydantic import BaseModel, ConfigDict


class AgentCard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    description: str
    consumes: tuple[str, ...] = ()
    produces: tuple[str, ...] = ()
    specs: tuple[str, ...] = ()
    allowed_materials: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    memory_namespaces: tuple[str, ...] = ()
