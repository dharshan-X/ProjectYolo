import os
import glob
import re

dest_dir = os.path.expanduser('~/.yolo/prompts')

files = glob.glob(os.path.join(dest_dir, '**/*.md'), recursive=True)

# ProjectYolo tools mapping
replacements = {
    r'\bview_file\b': 'read_file',
    r'\bmulti_replace_file_content\b': 'edit_file',
    r'\bgrep_search\b': 'search_in_file',
    r'\brun_command\b': 'run_bash',
    r'\bweb_fetch\b': 'browse_url',
    r'\bglob\b': 'codebase_search',
    r'\bGlob\b': 'codebase_search',
    r'\bNotebookEdit\b': 'edit_file',
    r'\bbrowse_urling\b': 'fetching', # Fix double mapping if any
}

processed = 0
for file_path in files:
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    new_content = content
    for pattern, replacement in replacements.items():
        new_content = re.sub(pattern, replacement, new_content)
    
    if new_content != content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        processed += 1

print(f"Updated {processed} files in {dest_dir} to match ProjectYolo tools.")
