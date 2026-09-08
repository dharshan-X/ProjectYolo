from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from PIL import Image
from tools.gui.models import DisplayLayout


class PlatformBackend(ABC):
    """Abstract interface for OS-level GUI perception and interaction."""

    @abstractmethod
    def get_display_layout(self) -> DisplayLayout:
        """Discover connected monitors and screen geometry."""
        pass

    @abstractmethod
    def take_screenshot(self, save_path: Optional[str] = None) -> Image.Image:
        """Capture the screen as a PIL Image."""
        pass

    @abstractmethod
    def get_active_windows(self) -> List[Dict[str, Any]]:
        """Return list of active windows with geometry and title."""
        pass

    @abstractmethod
    def emit_click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> None:
        """Emit mouse click."""
        pass

    @abstractmethod
    def emit_type(self, text: str, interval: float = 0.0) -> None:
        """Type text string."""
        pass

    @abstractmethod
    def emit_key(self, key: str) -> None:
        """Press key or key combination."""
        pass

    @abstractmethod
    def emit_scroll(self, clicks: int, x: int, y: int) -> None:
        """Scroll mouse wheel."""
        pass

    @abstractmethod
    def emit_drag(self, start_x: int, start_y: int, end_x: int, end_y: int, duration: float = 0.5) -> None:
        """Drag mouse cursor from start to end coordinates."""
        pass
