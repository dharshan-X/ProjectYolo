import os
import glob
import re
import shutil

src_dir = 'reference_prompts/system-prompts'
dest_dir = os.path.expanduser('~/.yolo/system-prompts')

os.makedirs(dest_dir, exist_ok=True)

files = glob.glob(os.path.join(src_dir, '**/*.md'), recursive=True)

for file_path in files:
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Replace Claude Code with Yolo
    content = re.sub(r'Claude Code', 'Yolo', content, flags=re.IGNORECASE)
    # Replace Claude with Yolo
    content = re.sub(r'Claude', 'Yolo', content, flags=re.IGNORECASE)
    # Replace Anthropic with ProjectYolo
    content = re.sub(r'Anthropic', 'ProjectYolo', content, flags=re.IGNORECASE)
    
    # Extract just the filename to save in dest_dir
    rel_path = os.path.relpath(file_path, src_dir)
    dest_path = os.path.join(dest_dir, rel_path)
    
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    
    with open(dest_path, 'w', encoding='utf-8') as f:
        f.write(content)
        
print(f"Processed {len(files)} files and saved them to {dest_dir}")
