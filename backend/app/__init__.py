import json
from pathlib import Path

# Single app version, shared with the frontend: the root package.json is the only source.
__version__: str = json.loads(
    (Path(__file__).resolve().parents[2] / "package.json").read_text(encoding="utf-8")
)["version"]
