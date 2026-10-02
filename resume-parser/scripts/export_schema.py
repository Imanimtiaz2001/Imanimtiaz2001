import json
from pathlib import Path

from clearcv.schemas import StoredResume

if __name__ == "__main__":
    Path("docs/schema.json").write_text(
        json.dumps(StoredResume.model_json_schema(), indent=2) + "\n"
    )
