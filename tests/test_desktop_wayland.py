import json
import shutil
import subprocess
from pathlib import Path


def test_electron_main_js_ozone_switches():
    main_js_path = Path("desktop/main.js")
    assert main_js_path.exists(), "desktop/main.js does not exist"
    main_js = main_js_path.read_text(encoding="utf-8")

    # Verify Ozone switches and environment variables
    assert "ozone-platform-hint" in main_js
    assert "WaylandWindowDecorations" in main_js
    assert "YOLO_ELECTRON_OZONE" in main_js
    assert "WAYLAND_DISPLAY" in main_js
    assert "XDG_SESSION_TYPE" in main_js
    assert "app.commandLine.appendSwitch" in main_js
    assert "(process.env.XDG_SESSION_TYPE || '').toLowerCase() === 'wayland'" in main_js


def test_electron_main_js_syntax():
    node_bin = shutil.which("node")
    if node_bin:
        result = subprocess.run(
            [node_bin, "-c", "desktop/main.js"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Node syntax check failed: {result.stderr}"


def test_electron_package_json_scripts():
    pkg_path = Path("desktop/package.json")
    assert pkg_path.exists(), "desktop/package.json does not exist"
    pkg_data = json.loads(pkg_path.read_text(encoding="utf-8"))

    scripts = pkg_data.get("scripts", {})
    assert "start" in scripts, "start script missing in desktop/package.json"
    assert "dev" in scripts, "dev script missing in desktop/package.json"
    assert "electron" in scripts["start"]
    assert "electron" in scripts["dev"]
