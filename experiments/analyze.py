# Analysis lives in manual inspection of JSONL files under experiments/results/.
# Each line is one trial record: {case, condition, repeat, iterations, compiled, correct, ...}
# Load with: import json; records = [json.loads(l) for l in open("experiments/results/<file>.jsonl")]
