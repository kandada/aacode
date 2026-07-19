# skill_creator

## Description
Meta-skill: how to create, update and optimize skills. Follow this guide whenever the user asks to add a new skill or improve an existing one.

## Parameters
- name: skill name — lowercase letters, digits and underscores only (e.g. api_tester)
- action: "create" or "update"

## Example
run_skills("skill_creator")

## Skill storage layout (two locations)

1. Project skills — specific to the current project:
   `<project>/skills/<skill_name>/SKILL.md`
2. User skills — reusable across all projects:
   - macOS:   `~/Library/Application Support/com.aacode/skills/<skill_name>/SKILL.md`
   - Linux:   `~/.config/com.aacode/skills/<skill_name>/SKILL.md`
   - Windows: `%APPDATA%\com.aacode\skills\<skill_name>\SKILL.md`

Default to the PROJECT location unless the user says the skill should be
available everywhere ("全局" / "所有项目" / "reusable across projects").

## Two kinds of skills

- Document skill: the directory contains only SKILL.md. run_skills returns the
  guide and the model follows it with shell/other tools. Start here — it is
  always safe.
- Script skill: SKILL.md plus a Python file (any `.py` name). The script's
  function is executed with the given params. Only create one when the logic
  genuinely needs code (imports are auto-injected per config).

## Required SKILL.md structure

```markdown
# <skill_name>

## Description
One sentence describing what this skill does.

## Parameters
- param1: description of param1
- param2: description of param2

## Example
run_skills("<skill_name>", {"param1": "value1", "param2": "value2"})
```

Optional sections (append AFTER the three required ones when the skill talks
to a remote service, e.g. a remote test sandbox):

```markdown
## Remote Endpoint
https://example.com/api

## Secret
<the secret or API key required by the endpoint>
```

## How to create a skill

1. Check for name conflicts first: run_skills("__list__") — if the name
   already exists, DO NOT overwrite it unless the user explicitly asked to
   modify/optimize that exact skill. Otherwise pick a different name.
2. Write the file (heredoc keeps formatting intact):

```
mkdir -p skills/my_skill && cat > skills/my_skill/SKILL.md <<'EOF'
# my_skill

## Description
...

## Parameters
- ...

## Example
run_skills("my_skill", {...})
EOF
```

3. Verify: run_skills("__info__", {"skill_name": "my_skill"}) — confirm the
   content is complete and well-formed. Changes take effect immediately, no
   restart needed.

## How to update / optimize a skill

1. Read the current version: run_skills("__info__", {"skill_name": "x"}).
2. Rewrite the full SKILL.md (same heredoc pattern). Keep the required
   section structure; preserve the existing "## Remote Endpoint" and
   "## Secret" sections unless the user asked to change them.
3. For script skills, update the `.py` alongside SKILL.md and keep the two
   consistent.

## Rules

- Skill names: ^[a-z][a-z0-9_]*$ — no spaces, no dashes, no uppercase.
- Never copy a "## Secret" value into any other file, command output or
  message; it may only exist inside its own SKILL.md.
- Keep Description to one line — it is shown in every system prompt; details
  belong in the body (progressive disclosure keeps context small).
