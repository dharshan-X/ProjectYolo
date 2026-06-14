import json
import os
from pathlib import Path

def migrate():
    env_path = Path("/home/dharshan/project-Yolo/.env")
    settings_path = Path.home() / ".yolo" / "settings.json"
    
    settings = {}
    if settings_path.exists():
        with open(settings_path, 'r') as f:
            settings = json.load(f)
            
    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    # Handle lines starting with '### ' or similar as comments
                    if line.startswith('###'):
                        continue
                    if '=' in line:
                        key, val = line.split('=', 1)
                        settings[key.strip()] = val.strip().strip("'\"")
    
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    with open(settings_path, 'w') as f:
        json.dump(settings, f, indent=4)
        
    print(f"Migrated to {settings_path}")

if __name__ == "__main__":
    migrate()
