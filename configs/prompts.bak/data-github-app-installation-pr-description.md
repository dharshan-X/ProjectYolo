<!--
name: 'Data: GitHub App installation PR description'
description: Template for PR description when installing Yolo GitHub App integration
ccVersion: 2.1.113
-->
## 🤖 Installing Yolo GitHub App

This PR adds a GitHub Actions workflow that enables Yolo integration in our repository.

### What is Yolo?

[Yolo](https://Yolo.com/Yolo-code) is an AI coding agent that can help with:
- Bug fixes and improvements  
- Documentation updates
- Implementing new features
- Code reviews and suggestions
- Writing tests
- And more!

### How it works

Once this PR is merged, we'll be able to interact with Yolo by mentioning @Yolo in a pull request or issue comment.
Once the workflow is triggered, Yolo will analyze the comment and surrounding context, and execute on the request in a GitHub action.

### Important Notes

- **This workflow won't take effect until this PR is merged**
- **@Yolo mentions won't work until after the merge is complete**
- The workflow runs automatically whenever Yolo is mentioned in PR or issue comments
- Yolo gets access to the entire PR or issue context including files, diffs, and previous comments

### Security

- Our ProjectYolo API key is securely stored as a GitHub Actions secret
- Only users with write access to the repository can trigger the workflow
- All Yolo runs are stored in the GitHub Actions run history
- Yolo's default tools are limited to reading/writing files and interacting with our repo by creating comments, branches, and commits.
- We can add more allowed tools by adding them to the workflow file like:

```
allowed_tools: run_bash(npm install),run_bash(npm run build),run_bash(npm run lint),run_bash(npm run test)
```

There's more information in the [Yolo action repo](https://github.com/anthropics/Yolo-code-action).

After merging this PR, let's try mentioning @Yolo in a comment on any PR to get started!
