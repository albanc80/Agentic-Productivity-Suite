# ADR 0007: Ship the agent pack encrypted in the installers

Status: accepted · 2026-11-08 · partly supersedes ADR 0005 ("installers never bundle it")

## Context
ADR 0005 took the agents' instructions, personas and lineage out of the public repository and the
installers. Every computer then had to import the pack by hand, and an installed app showed
"Not installed" while its agents ran on their public descriptions: about 700 characters of system prompt
for the Chief of Staff instead of about 23,000. The owner's goal is different: hide the instructions
from the UI and the public source, and keep them inside the app so agents work fully with no setup.

## Decision
- The pack (`agents/<agent-id>.yaml`, the same format as ADR 0005) is encrypted with AES-256-GCM and
  committed as `registry/agent-pack.enc`. The plain pack and the key are never committed (`.gitignore`,
  a test checks both).
- The key is 32 random bytes held in the `AGENT_PACK_KEY` repository secret. The installer build
  (`desktop/bundle_agent_key.py`) checks that it opens the pack, fails the build if not, and writes it to
  `config/agent-pack.key` inside the bundle. The smoke test then requires all 34 agents built in.
- At runtime the app decrypts the pack in memory only; nothing decrypted is written to disk. A pack
  imported in Settings still works and replaces the built-in file for each agent it contains.
- `/api/*` never returns instructions, personas, lineage or the key (unchanged from ADR 0005).
- The owner manages the pack with `scripts/agent_pack.py` (`genkey`, `encrypt`, `check`, `decrypt`).
  The committed file plus the key is also the backup of the pack.

## What this protects, and what it does not
- Protects against: reading the instructions in the public repository, in the installer's files, in the
  app's screens or API, or by copying the data folder.
- Does not protect against: someone who unpacks an installer, finds the key and decrypts the pack.
  The key has to travel with the app for the agents to use the instructions, so this deters casual
  copying only. The instructions are also sent to the chosen model provider in every call, and they are
  kept in the audit log if "store prompts" is switched on (it is off by default).
- Stronger options, if needed later: make the repository and its releases private, or serve the
  instructions from a server you control (which would break offline use).

## Consequences
- Releases built without the secret still work; their agents use their public descriptions and
  Settings says so.
- Changing the instructions: edit the plain pack you keep, run `agent_pack.py encrypt`, commit
  `registry/agent-pack.enc`, raise the version.
- Losing the key makes `agent-pack.enc` unreadable. Keep the key and the plain pack backed up privately.
- Rotating the key means encrypting again and updating the secret; installers already published keep the old key.
