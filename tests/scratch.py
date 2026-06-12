import os

def process_file(filepath, pattern, prefix, start_code):
    with open(filepath, "r") as f:
        content = f.read()
    
    code = start_code
    
    def replacer(match):
        nonlocal code
        c = code
        code += 1
        
        # We need to find the matching closing parenthesis for the call
        text = content[match.end():]
        parens = 1
        i = 0
        while i < len(text) and parens > 0:
            if text[i] == '(': parens += 1
            elif text[i] == ')': parens -= 1
            i += 1
            
        inner = text[:i-1]
        
        # if it already has code=, don't change
        if "code=" in inner:
            return match.group(0) + inner + ")"
            
        return match.group(0) + inner + f', code="E{c}"' + ")"

    import re
    # Match the start of the call
    new_content = ""
    last_end = 0
    for match in re.finditer(pattern, content):
        new_content += content[last_end:match.start()]
        
        c = code
        code += 1
        
        # manual parsing to find matching parens
        text = content[match.end():]
        parens = 1
        i = 0
        in_string = False
        string_char = ''
        escape = False
        while i < len(text) and parens > 0:
            char = text[i]
            if escape:
                escape = False
            elif char == '\\':
                escape = True
            elif in_string:
                if char == string_char:
                    in_string = False
            else:
                if char in '"\'':
                    in_string = True
                    string_char = char
                elif char == '(': parens += 1
                elif char == ')': parens -= 1
            i += 1
            
        inner = text[:i-1]
        if "code=" in inner:
            new_content += match.group(0) + inner + ")"
            code -= 1 # revert
        else:
            new_content += match.group(0) + inner + f', code="E{c}"' + ")"
            
        last_end = match.end() + i - 1
        
    new_content += content[last_end:]
    
    with open(filepath, "w") as f:
        f.write(new_content)

process_file("src/oda/semantic.py", r"self\._err\(", 3, 3010)
process_file("src/oda/importer.py", r"raise SemanticError\(", 4, 4001)
# process_file("src/oda/codegen.py", r"raise CodegenError\(", 5, 5001)

