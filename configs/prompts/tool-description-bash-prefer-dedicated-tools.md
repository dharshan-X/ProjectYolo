<!--
name: 'Tool Description: run_bash (prefer dedicated tools)'
description: Warning to prefer dedicated tools over run_bash for find, grep, cat, etc.
ccVersion: 2.1.71
variables:
  - READ_ONLY_SEARCHING_BASH_COMMANDS
-->
IMPORTANT: Avoid using this tool to run ${READ_ONLY_SEARCHING_BASH_COMMANDS} commands, unless explicitly instructed or after you have verified that a dedicated tool cannot accomplish your task. Instead, use the appropriate dedicated tool as this will provide a much better experience for the user:
