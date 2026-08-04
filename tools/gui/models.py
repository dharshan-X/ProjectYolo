import json
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from enum import Enum

class GUIErrorReason(Enum):
    ELEMENT_NOT_FOUND = "element_not_found"
    AMBIGUOUS_MATCH = "ambiguous_match"
    STALE_STATE = "stale_state"
    OUT_OF_BOUNDS = "out_of_bounds"
    VERIFICATION_FAILED = "verification_failed"
    BACKEND_ERROR = "backend_error"

@dataclass
class BoundingBox:
    x: int
    y: int
    width: int
    height: int

    @property
    def center_x(self) -> int:
        return self.x + self.width // 2

    @property
    def center_y(self) -> int:
        return self.y + self.height // 2

@dataclass
class Monitor:
    name: str
    x: int
    y: int
    width: int
    height: int
    is_primary: bool

@dataclass
class DisplayLayout:
    monitors: List[Monitor]
    virtual_width: int
    virtual_height: int

@dataclass
class GUIWindow:
    id: str
    title: str
    bounds: BoundingBox
    is_active: bool
    app_name: Optional[str] = None

@dataclass
class UIElement:
    id: str
    text: str
    type: str
    bounds: BoundingBox
    source: str  # "atspi", "ocr", "merged"
    confidence: float = 1.0
    properties: Dict[str, Any] = field(default_factory=dict)

@dataclass
class GUIState:
    state_id: str
    timestamp: float
    screenshot_path: Optional[str]
    annotated_path: Optional[str]
    windows: List[GUIWindow]
    active_window: Optional[GUIWindow]
    elements: List[UIElement]
    layout: DisplayLayout

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class GroundingResult:
    target: Optional[UIElement]
    confidence: float
    margin: float
    status: str  # "success", "ambiguous", "not_found"
    candidates: List[UIElement] = field(default_factory=list)
    reason: Optional[str] = None
