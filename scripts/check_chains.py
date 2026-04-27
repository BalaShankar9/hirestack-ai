import re, glob
for f in sorted(glob.glob('ai_engine/chains/*.py')):
    with open(f) as fh:
        content = fh.read()
    calls = len(re.findall(r'\.format\(', content))
    print(f'{f}: .format()={calls}')
    # Check for true/false in JSON (Python uses True/False) - this is fine in prompts
    # Check for unescaped single { in prompt strings
    lines = content.split('\n')
    for i, line in enumerate(lines, 1):
        # Skip lines that are code, look at triple-quoted string content
        stripped = line.strip()
        if '.format(' in stripped:
            print(f'  Line {i}: {stripped[:80]}')
