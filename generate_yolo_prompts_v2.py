import os
import glob
import re
import shutil

src_dir = 'reference_prompts/system-prompts'
dest_dir = os.path.expanduser('~/.yolo/prompts')

os.makedirs(dest_dir, exist_ok=True)

files = glob.glob(os.path.join(src_dir, '**/*.md'), recursive=True)

# Remove the old incorrect directory if it exists
old_dir = os.path.expanduser('~/.yolo/system-prompts')
if os.path.exists(old_dir):
    shutil.rmtree(old_dir)

# Mapping of tools and terminology
replacements = {
    # Names
    r'\bClaude Code\b': 'Yolo',
    r'\bClaude\b': 'Yolo',
    r'\bAnthropic\b': 'ProjectYolo',
    r'\bclaudemd\b': 'yolomd',
    r'\bCLAUDE\.md\b': 'YOLO.md',
    
    # Tools mapping
    r'\bRead tool\b': '`view_file` tool',
    r'\bRead\b': 'view_file',
    r'\bEdit tool\b': '`multi_replace_file_content` tool',
    r'\bEdit\b': 'multi_replace_file_content',
    r'\bGrep tool\b': '`grep_search` tool',
    r'\bGrep\b': 'grep_search',
    r'\bBash tool\b': '`run_command` tool',
    r'\bBash\b': 'run_command',
    r'\bbash\b': 'run_command',
}

def transform_content(content):
    for pattern, replacement in replacements.items():
        # Using regex with ignore case for some, but specific case for tools to avoid over-replacing
        if "Claude" in pattern or "Anthropic" in pattern or "claudemd" in pattern:
             content = re.sub(pattern, replacement, content, flags=re.IGNORECASE)
        else:
             content = re.sub(pattern, replacement, content)
    return content

processed = 0
for file_path in files:
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    content = transform_content(content)
    
    # Also rename the file if it contains claude
    filename = os.path.basename(file_path)
    new_filename = re.sub(r'claude', 'yolo', filename, flags=re.IGNORECASE)
    new_filename = re.sub(r'anthropic', 'projectyolo', new_filename, flags=re.IGNORECASE)
    
    dest_path = os.path.join(dest_dir, new_filename)
    
    # Do not overwrite the base existing prompts from yolo if they happen to conflict
    if not os.path.exists(dest_path) or "base.md" not in dest_path:
        with open(dest_path, 'w', encoding='utf-8') as f:
            f.write(content)
        processed += 1
        
print(f"Processed {processed} files and saved them to {dest_dir}")
