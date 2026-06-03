DIR_OPTIONS=(
    "Current Directory ($PWD)"
    "Home Directory (~)"
    "Project Yolo Source (/home/dharshan/ProjectYolo)"
    "Search with fzf (Current Directory tree)"
    "Search with fzf (Home Directory tree)"
    "Type path manually"
)
for i in "${!DIR_OPTIONS[@]}"; do echo "$i: ${DIR_OPTIONS[$i]}"; done
