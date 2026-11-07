"""Topology Domain Models for Nawari Network Intelligence."""

from services.topology.models.change import (
    ChangeType,
    TargetEntityType,
    TopologyChange,
)
from services.topology.models.dependency import (
    Criticality,
    DependentType,
    FailureImpact,
    ServiceDependency,
)
from services.topology.models.device import (
    ConfidenceLevel,
    Device,
    DeviceType,
)
from services.topology.models.interface import (
    AdminStatus,
    Interface,
    OperStatus,
)
from services.topology.models.link import (
    DiscoveryProtocol,
    Layer2Link,
    LinkStatus,
    LinkType,
)
from services.topology.models.subnet import (
    RoutingAdjacency,
    Subnet,
)

__all__ = [
    "DeviceType",
    "ConfidenceLevel",
    "Device",
    "AdminStatus",
    "OperStatus",
    "Interface",
    "DiscoveryProtocol",
    "LinkType",
    "LinkStatus",
    "Layer2Link",
    "DependentType",
    "Criticality",
    "FailureImpact",
    "ServiceDependency",
    "ChangeType",
    "TargetEntityType",
    "TopologyChange",
    "Subnet",
    "RoutingAdjacency",
]

