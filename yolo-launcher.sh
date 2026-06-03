#!/bin/bash

# Hide cursor on exit if script is interrupted
trap 'tput cnorm; exit 1' INT

echo -e "\033[1;36m🚀 YOLO Interactive Launcher\033[0m"
echo "============================="

YOLO_BASE="/home/dharshan/ProjectYolo"

# Function to render an interactive arrow-key menu
interactive_menu() {
    local prompt="$1"
    shift
    local options=("$@")
    local selected=0
    local key

    # Hide cursor
    tput civis >&2

    # Print empty lines so we have space to move up and down
    echo -e "\033[1;36m$prompt\033[0m" >&2
    for i in "${!options[@]}"; do
        echo "" >&2
    done
    
    # Move back up to start drawing
    tput cuu $((${#options[@]})) >&2

    while true; do
        for i in "${!options[@]}"; do
            # Clear line
            tput el >&2
            if [ $i -eq $selected ]; then
                echo -e "  \033[1;32m➜ ${options[$i]}\033[0m" >&2
            else
                echo -e "    ${options[$i]}" >&2
            fi
        done

        # Read keystroke
        read -rsn1 key < /dev/tty

        if [[ $key == $'\x1b' ]]; then
            read -rsn2 key < /dev/tty # read [A or [B
            case "$key" in
                '[A') ((selected--));; # Up
                '[B') ((selected++));; # Down
            esac
        elif [[ $key == "" ]]; then # Enter key
            break
        fi

        # Boundary checks
        if [ $selected -lt 0 ]; then
            selected=$((${#options[@]} - 1))
        elif [ $selected -ge ${#options[@]} ]; then
            selected=0
        fi

        # Move cursor up to overwrite
        tput cuu ${#options[@]} >&2
    done

    # Move cursor past the menu so subsequent output is below it
    # No need to move down since the loop just printed all lines

    # Show cursor
    tput cnorm >&2

    # Echo selected index (0-based) to stdout
    echo "$selected"
}

# Function to browse directories step-by-step using fzf
interactive_fzf_browser() {
    local dir="$1"
    while true; do
        local selection
        selection=$( (echo -e "\033[1;32m. (Select this directory)\033[0m"; echo -e "\033[1;33m.. (Go up)\033[0m"; find "$dir" -maxdepth 1 -mindepth 1 -type d ! -name ".*" -printf "%f\n" | sort) | fzf --ansi --prompt="Browsing: $dir > " --height=40% --layout=reverse --border=rounded )
        
        if [ -z "$selection" ]; then
            # User aborted (pressed ESC)
            return
        elif [[ "$selection" == *". (Select this directory)"* ]]; then
            echo "$dir"
            return
        elif [[ "$selection" == *".. (Go up)"* ]]; then
            dir=$(realpath "$dir/..")
        else
            dir=$(realpath "$dir/$selection")
        fi
    done
}

# --- 1. DIRECTORY SELECTION ---

DIR_OPTIONS=(
    "Current Directory ($PWD)"
    "Home Directory (~)"
    "Project Yolo Source ($YOLO_BASE)"
    "🔍 Step-by-step fzf (from Current Directory)"
    "🔍 Step-by-step fzf (from Home Directory)"
    "Type path manually"
)

DIR_CHOICE=$(interactive_menu "Where would you like Yolo to operate?" "${DIR_OPTIONS[@]}")

case "$DIR_CHOICE" in
    1) WORK_DIR="$HOME" ;;
    2) WORK_DIR="$YOLO_BASE" ;;
    3) 
        if ! command -v fzf &> /dev/null; then
            echo -e "\033[1;31mError: fzf is not installed. Please install it with 'sudo apt install fzf'.\033[0m"
            exit 1
        fi
        WORK_DIR=$(interactive_fzf_browser "$PWD" | tail -n 1)
        [ -z "$WORK_DIR" ] && { echo "Aborted."; exit 1; }
        ;;
    4) 
        if ! command -v fzf &> /dev/null; then
            echo -e "\033[1;31mError: fzf is not installed. Please install it with 'sudo apt install fzf'.\033[0m"
            exit 1
        fi
        WORK_DIR=$(interactive_fzf_browser "$HOME" | tail -n 1)
        [ -z "$WORK_DIR" ] && { echo "Aborted."; exit 1; }
        ;;
    5)
        # We need to re-enable cursor for input
        tput cnorm >&2
        echo ""
        read -e -p "Enter path: " INPUT_DIR < /dev/tty
        WORK_DIR="${INPUT_DIR/#\~/$HOME}"
        ;;
    *) WORK_DIR="$PWD" ;;
esac

# Ensure target directory exists
if [ ! -d "$WORK_DIR" ]; then
    echo -e "\n\033[1;33mDirectory '$WORK_DIR' does not exist.\033[0m"
    read -p "Do you want to create it? (y/n) [y]: " CREATE_DIR < /dev/tty
    CREATE_DIR=${CREATE_DIR:-y}
    if [[ "$CREATE_DIR" =~ ^[Yy]$ ]]; then
        mkdir -p "$WORK_DIR"
    else
        echo "Aborting."
        exit 1
    fi
fi

WORK_DIR=$(realpath "$WORK_DIR")
echo -e "\n📂 Working directory set to: \033[1;32m$WORK_DIR\033[0m\n"

# --- 2. INTERFACE SELECTION ---

INT_OPTIONS=(
    "CLI (Standard Terminal)"
    "TUI (Textual Dashboard)"
    "Telegram Bot"
    "Discord Bot"
    "Desktop App (Electron)"
    "All Gateways (Server Mode)"
)

INT_CHOICE=$(interactive_menu "Select interface to launch:" "${INT_OPTIONS[@]}")

case "$INT_CHOICE" in
    1) CMD="python3 $YOLO_BASE/tui.py" ;;
    2) CMD="python3 $YOLO_BASE/bot.py" ;;
    3) CMD="python3 $YOLO_BASE/discord_gateway.py" ;;
    4) 
       export YOLO_CWD="$WORK_DIR"
       CMD="npm start --prefix $YOLO_BASE/desktop" 
       ;;
    5) CMD="python3 $YOLO_BASE/server.py --mode all" ;;
    *) CMD="python3 $YOLO_BASE/cli.py" ;;
esac

echo -e "\n\033[1;36mStarting YOLO...\033[0m"
cd "$WORK_DIR" || exit 1
eval "$CMD"
