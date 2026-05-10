---
name: add-model
description: |
  Add a new local LLM to the llmops registry on this host. Use when the
  user says any of: "set up X model", "add the Qwen 14B", "download
  Qwen3-Coder", "add a model", "I want to try Y model locally",
  "register Z in models.toml". Resolves a vague reference to a specific
  HuggingFace GGUF file, picks a sensible quant + ctx + port, downloads
  the GGUF, writes the models.toml entry, and smoke-tests via
  `llmops use`. Lives in ~/llmops/skills/ so it ports across machines.
author: Claude Code (in-repo skill)
version: 1.0.0
date: 2026-05-10
---

# add-model

## Goal

When the user wants a new model added to their llmops install on this host,
do the full setup in one shot: resolve, download, register, smoke-test,
report the endpoint. Be conversational, not robotic — confirm choices
that matter (which variant, which quant) and quietly handle the rest.

## Trigger conditions

Activate when the user says anything like:
- "set up <model> now"
- "add <model> to my registry / models.toml"
- "download <model>"
- "I want to try <model> locally"
- "register / install / pull <model>"

If you're not sure whether they want it added permanently or just tried once,
ask before downloading multi-GB files.

## Steps

### 1. Resolve the reference to a concrete HuggingFace repo + file

The user will say something vague ("the Qwen 14B Coder", "the bigger Qwen",
"that 30B MoE one"). Your job is to land on one specific GGUF file.

- **Default vendor: Unsloth.** The existing registry uses their UD-* quants.
  Stay consistent unless the user asks otherwise. The Unsloth HF org is
  `unsloth/<Model>-GGUF`.
- **Default quant: `UD-Q4_K_XL`.** Best quality-to-VRAM ratio for the
  Unsloth Dynamic 2.0 lineup. Drop to `UD-Q3_K_XL` only if VRAM is tight.
- **Verify the repo and file actually exist** with WebFetch on
  `https://huggingface.co/<repo>` — list the GGUF files. Pick the matching
  variant. Don't guess filenames; HF returns 404 silently sometimes and
  curl will save the HTML error page as a `.gguf`.

If the user is vague between sizes, surface a short menu with VRAM
implications relative to the host's GPU(s) (use `nvidia-smi` output from
`llmops host`).

### 2. Verify VRAM fit

Run `llmops host` to see GPU inventory. Estimate `min_vram_gb`:

- Weights = GGUF file size on disk (in GB). HF's file listing shows this.
- KV cache at q8_0 for typical Qwen-family ctx values:
  - 32K ctx → ~1.5-2 GB
  - 16K ctx → ~0.8-1 GB
  - 8K ctx → ~0.4 GB
- Add ~0.5 GB overhead for the runtime itself.
- Round up to nearest 0.5 GB.

If no GPU on the host fits the model, **stop and tell the user**. Offer:
- A smaller quant (UD-Q3_K_XL, UD-Q2_K_XL)
- A smaller variant of the same model family
- "Just download it, don't try to run it yet" (e.g. waiting on a 3090)

Don't burn bandwidth downloading something that can't run.

### 3. Pick defaults

Write a TOML entry for `models.toml`. Defaults:

- **Registry key + alias**: same string, lowercased, family-prefixed.
  Examples: `qwen3.5-14b`, `qwen3.5-coder-7b`, `qwen3-coder-next`.
  Match the existing naming convention (look at `models.toml` first).
- **Port**: next unused port at or above 8080. Run
  `grep -E '^port' models.toml` to see what's taken.
- **ctx_size**: 32768 for ≤9B, 16384 for 14B-27B, 8192 for 30B+, or what
  the model card recommends.
- **kv_type**: `q8_0` always (set `q4_0` only if VRAM is genuinely tight).
- **Sampling**: temperature 0.2-0.3 for executor-style models, 0.3-0.6 for
  reasoning/chat models. Always `top_p = 0.8`, `top_k = 20` (Qwen defaults).
- **Description**: one short line, e.g. "Coder variant — agentic coding,
  function calling, repo-scale edits".

### 4. Download the GGUF

```bash
curl -L --retry-all-errors --fail \
  -o "$LLM_GGUF_DIR/<exact-filename>.gguf" \
  "https://huggingface.co/<repo>/resolve/main/<exact-filename>.gguf"
```

- `--retry-all-errors` is critical. A mid-stream connection break silently
  truncates the file otherwise.
- Resolve `$LLM_GGUF_DIR` from the host config (look at
  `hosts/<hostname>.toml`'s `gguf_dir`, or default to `~/llm-models/gguf`).
- Show the user the size before downloading anything over ~5 GB.

### 5. Write the models.toml entry

Append the new section to `models.toml`. Preserve the existing order
(smallest to largest is the convention). The TOML key must be quoted if
it contains a period (e.g. `[models."qwen3.5-14b"]`).

### 6. Smoke-test

Run `llmops use <name>` and wait for `/health`. On success, send a
single short chat completion to confirm it serves tokens. Use
`chat_template_kwargs: {enable_thinking: false}` to avoid the empty-content
trap (see CHEATSHEET — Qwen3.5 enables thinking by default, all output goes
to `reasoning_content` if you forget this).

If smoke test passes: report the endpoint URL and ask whether to leave
it running or stop it.
If smoke test fails: show `docker logs llmops-<name>-gpu<N>` tail, don't
silently leave a broken container behind.

### 7. Don't auto-commit

The user reviews TOML changes themselves. Show them the diff, don't
`git add` or `git commit`.

## Examples

### Example A: clear request

User: "set up Qwen3.5-14B now"

You:
1. WebFetch `https://huggingface.co/unsloth/Qwen3.5-14B-GGUF` — confirm
   `Qwen3.5-14B-UD-Q4_K_XL.gguf` exists, get file size (~9 GB).
2. Run `llmops host` — only the 3080 (10 GiB) is available right now.
3. 14B Q4 weights ~9 GB + 1 GB KV + 0.5 overhead = ~10.5 GB. **Won't fit
   on 10 GiB.** Surface to user: "won't fit on the 3080; either wait for
   the 3090 or use UD-Q3_K_XL (~7 GB total) now."

### Example B: ambiguous request

User: "add the Coder model"

You: "Two real options today — Qwen3-Coder-Next (80B MoE, 3B active,
needs ~24 GB) or Qwen2.5-Coder-14B (dense, ~9 GB). The 80B MoE is the
flagship for agentic coding; only fits on the 3090. Which?"

### Example C: clean fit

User: "grab the Qwen3.5-2B"

You:
1. Verify on HF: `Qwen3.5-2B-UD-Q4_K_XL.gguf` (~1.4 GB).
2. Picks port 8082 (next free after 8079, 8080, 8081).
3. `min_vram_gb = 2.5`, ctx_size 32768, kv_type q8_0.
4. Download to `~/llm-models/gguf/`.
5. Add `[models."qwen3.5-2b"]` block.
6. `llmops use qwen3.5-2b` — healthy → smoke chat → report endpoint.
7. Ask: leave running or stop? Default to stop (free VRAM).

## Notes / gotchas

- The Unsloth `-hf <repo>` shorthand in llama.cpp **does not work** for
  these repos (404s on the manifest). Always pre-download + mount. The
  CLI runner does this correctly already.
- Qwen3.5 has thinking-mode-on by default. Empty `content` with the
  actual response in `reasoning_content` is the symptom. Cure:
  `chat_template_kwargs: {enable_thinking: false}` in the smoke test.
- llama.cpp recently renamed speculative-decoding flags
  (`--draft-max` → `--spec-draft-n-max`). Not relevant for `add-model`
  itself but be aware if the user asks to test the new model as a
  draft or target.
- Skill lives in the llmops repo at `~/llmops/skills/add-model/`. To
  make it discoverable by Claude Code on a new machine, symlink it
  into `~/.claude/skills/` via `~/llmops/scripts/install-skills.sh`.

## References

- Unsloth Qwen3.5 documentation: https://unsloth.ai/docs/models/qwen3.5
- Unsloth HF org: https://huggingface.co/unsloth
- llama.cpp server flags: `docker run --rm --entrypoint /app/llama-server ghcr.io/ggml-org/llama.cpp:server-cuda --help`
