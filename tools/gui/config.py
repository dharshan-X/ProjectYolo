from dataclasses import dataclass
import os

@dataclass
class GUIConfig:
    min_match_confidence: float = 0.82
    min_match_margin: float = 0.12

    action_timeout_seconds: float = 5.0
    stability_poll_seconds: float = 0.2
    stability_required_polls: int = 3

    max_action_attempts: int = 2
    max_elements: int = 200

    enable_atspi: bool = os.environ.get("GUI_ENABLE_ATSPI", "1") == "1"
    enable_ocr: bool = os.environ.get("GUI_ENABLE_OCR", "1") == "1"

    save_debug_artifacts: bool = os.environ.get("GUI_SAVE_ARTIFACTS", "1") == "1"

    # Weights for matching
    weight_text: float = 0.55
    weight_role: float = 0.15
    weight_spatial: float = 0.10
    weight_window: float = 0.10
    weight_context: float = 0.10

    @classmethod
    def load(cls) -> "GUIConfig":
        return cls()
