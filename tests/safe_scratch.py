import os
import re

def process_file(filepath, pattern, prefix, start_code):
    with open(filepath, "r") as f:
        content = f.read()
    
    code = start_code
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
            
        inner = text[:i-1] # without the closing parenthesis
        if "code=" in inner:
            new_content += match.group(0) + inner + ")"
            code -= 1 # revert
        else:
            # We must be careful: inner might already end with `)` if parens calculation is wrong?
            # but parens matching is usually correct.
            new_content += match.group(0) + inner + f', code="E{c}"' + ")"
            
        last_end = match.end() + i - 1 # up to before the closing parenthesis we consumed?
        # actually match.end() + i is the character after the closing parenthesis.
        # wait, i is the length of the string up to the closing parenthesis inclusive.
        # so text[:i] includes the closing parenthesis.
        # wait! text[i-1] IS the closing parenthesis.
        last_end = match.end() + i
        
    new_content += content[last_end:]
    
    with open(filepath, "w") as f:
        f.write(new_content)

process_file("src/oda/semantic.py", r"self\._err\(", 3, 3001)
process_file("src/oda/importer.py", r"raise SemanticError\(", 4, 4001)

