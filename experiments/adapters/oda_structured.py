import json
import subprocess
from pathlib import Path

def get_feedback(oda_source_path: str) -> tuple[bool, str]:
    repo_root = Path(__file__).resolve().parent.parent.parent
    oda_bin = repo_root / "oda"
    
    result = subprocess.run(
        [str(oda_bin), "transpile", str(oda_source_path), "--output-format=json"],
        capture_output=True,
        text=True
    )
    
    try:
        data = json.loads(result.stdout)
        if isinstance(data, dict) and data.get("success") is True:
            return True, ""
    except json.JSONDecodeError:
        pass
        
    feedback = result.stdout.strip()
    if not feedback:
        stderr_msg = result.stderr.strip()
        feedback = json.dumps({
            "success": False,
            "errors": [{
                "code": "COMPILER_ERROR",
                "message": stderr_msg or "Unknown transpilation failure",
                "line": 1,
                "column": 1
            }]
        })
        
    return False, feedback
