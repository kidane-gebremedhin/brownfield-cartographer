from __future__ import annotations
from pydantic import BaseModel, Field
from models.edges import TypedEdge
from models.nodes import DatasetNode, FunctionNode, ModuleNode, TransformationNode


class ModuleGraph(BaseModel):
    module_nodes: list[ModuleNode] = Field(default_factory=list)
    function_nodes: list[FunctionNode] = Field(default_factory=list)
    edges: list[TypedEdge] = Field(default_factory=list)
    model_config = {"extra": "forbid"}


class DataLineageGraph(BaseModel):
    dataset_nodes: list[DatasetNode] = Field(default_factory=list)
    transformation_nodes: list[TransformationNode] = Field(default_factory=list)
    edges: list[TypedEdge] = Field(default_factory=list)
    model_config = {"extra": "forbid"}
