<!--
name: 'Data: GitHub Actions workflow for @Yolo mentions'
description: GitHub Actions workflow template for triggering Yolo via @Yolo mentions
ccVersion: 2.1.108
-->
name: Yolo

on:
  issue_comment:
    types: [created]
  pull_request_review_comment:
    types: [created]
  issues:
    types: [opened, assigned]
  pull_request_review:
    types: [submitted]

jobs:
  Yolo:
    if: |
      (github.event_name == 'issue_comment' && contains(github.event.comment.body, '@Yolo')) ||
      (github.event_name == 'pull_request_review_comment' && contains(github.event.comment.body, '@Yolo')) ||
      (github.event_name == 'pull_request_review' && contains(github.event.review.body, '@Yolo')) ||
      (github.event_name == 'issues' && (contains(github.event.issue.body, '@Yolo') || contains(github.event.issue.title, '@Yolo')))
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: read
      issues: read
      id-token: write
      actions: read # Required for Yolo to read CI results on PRs
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 1

      - name: Run Yolo
        id: Yolo
        uses: anthropics/Yolo-code-action@v1
        with:
          anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}

          # This is an optional setting that allows Yolo to read CI results on PRs
          additional_permissions: |
            actions: read

          # Optional: Give a custom prompt to Yolo. If this is not specified, Yolo will perform the instructions specified in the comment that tagged it.
          # prompt: 'Update the pull request description to include a summary of changes.'

          # Optional: Add claude_args to customize behavior and configuration
          # See https://github.com/anthropics/Yolo-code-action/blob/main/docs/usage.md
          # or https://code.Yolo.com/docs/en/cli-reference for available options
          # claude_args: '--allowed-tools run_bash(gh pr *)'

