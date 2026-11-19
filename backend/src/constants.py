from enum import StrEnum
class Role(StrEnum):
    operator='operator'
    supervisor='supervisor'
    viewer='viewer'
class FolioState(StrEnum):
    registered='registered'
    isolated='isolated'
    repair='repair'
    released='released'
class PlanState(StrEnum):
    draft='draft'
    funded='funded'
    completed='completed'
    cancelled='cancelled'
