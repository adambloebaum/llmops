# Routing Policy

Authoritative rules for the local-agent-router (and any harness that talks
directly to the endpoints).

## Decision contract

Models do not execute tools. They return a single `AgentDecision`:

```json
{
  "kind": "tool_call | final | escalate | ask_user",
  "tool_name": "shell | read_file | write_file | list_files | grep | run_tests | none",
  "arguments": {},
  "rationale": "short reason",
  "risk": "low | medium | high",
  "confidence": 0.0,
  "codex_packet": null
}
```

Send this as `response_format: {type: "json_schema", schema: ...}`. See
`router/schema.py` for the canonical JSON Schema.

## Default route table

| Task type              | First model        | Escalate to smart when                     |
| ---------------------- | ------------------ | ------------------------------------------ |
| Parse shell output     | exec (4B)          | output is ambiguous or `confidence < 0.75` |
| Pick next command      | exec (4B)          | command has medium/high risk               |
| Summarize logs         | exec (4B)          | summary affects implementation strategy    |
| Inspect file           | exec (4B)          | needs multi-file reasoning                 |
| Small patch proposal   | exec (4B)          | more than one file or unclear side effects |
| Code review            | smart (9B)         | n/a                                        |
| Basic chat             | smart (9B)         | n/a                                        |
| Codex packet           | exec (4B)          | packet quality is poor or failure repeated |
| Final cloud escalation | smart prepares pkt | after local attempts fail                  |

## Escalation triggers (exec → smart)

Any of these flips the route to smart:

- JSON schema validation fails twice
- Model returns `confidence < 0.75`
- Model marks `risk` as `medium` or `high`
- Requested patch touches more than one file
- Task requires architectural reasoning
- Same test failure repeats after two local iterations
- Harness cannot verify the proposed action

## Cloud (Codex) triggers

Send to Codex only when:

- multi-file implementation
- nontrivial refactor
- unknown domain logic
- risky migration
- repeated failed local patch
- security-sensitive or data-loss-prone operation

## Tool policy

Allow without confirmation (read-only):

```
read_file, list_files, grep, run_tests
shell: pwd, ls, find, rg, git status, git diff,
       pytest ..., npm test ..., cargo test ...
```

Require confirmation or smart review:

```
write_file, apply_patch, package install, db commands, docker cleanup,
git reset, git checkout, git clean, rm, mv over existing files,
chmod / chown, network calls, deploy commands
```

Reject outright unless explicitly enabled:

```
rm -rf /, sudo destructive ops, credential exfiltration, git push,
production deploy, destructive db migration
```

## Codex packet shape

```
Goal:
- ...

Relevant files:
- path: why relevant

Observed failure:
- command:
- output summary:
- exact failing assertion/error:

Commands already run:
- ...

Facts learned:
- ...

Hypothesis:
- ...

Local attempts:
- ...

Requested Codex action:
- ...

Constraints:
- no unrelated refactors
- preserve existing behavior unless tests indicate otherwise
- include tests or update failing tests only if behavior intentionally changes
```

The harness must reject cloud escalation if the packet is missing any of:
goal, relevant files, observed failure, commands already run, facts learned,
requested action, constraints.
