## Description
Brief description of what this document skill guides the model to do.

## When to use
- Scenario 1: when the user needs ...
- Scenario 2: when the user asks about ...

## Workflow
1. First step: read relevant files, understand the context
2. Second step: use run_shell to execute commands
3. Third step: verify the results
4. Final step: report back to the user

## References
- `reference.md` - supplementary reference documentation
- `scripts/` - utility scripts for this workflow

## Examples
### Example 1
User: "Help me set up a new project"
Steps:
1. run_shell("mkdir my_project")
2. run_shell("cd my_project && git init")
3. ...

### Example 2
User: "Deploy the application"
Steps:
1. ...
