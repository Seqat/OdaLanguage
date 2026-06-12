import sys
for file in ["src/oda/semantic.py", "src/oda/importer.py"]:
    with open(file, "r") as f:
        content = f.read()
    content = content.replace('))', ')')
    with open(file, "w") as f:
        f.write(content)
