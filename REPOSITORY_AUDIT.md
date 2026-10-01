# Mercy repository cleanup audit

Source: `Butters26/Monday`, main commit `a3692c4e8b9e5c5159d6cda3f98b098a278ab259`.

The repository mixed a working direct-call core with historical snapshots,
duplicate agent instructions, an older memory implementation, disconnected
interfaces, and launch commands for obsolete sockets. The cleanup removes
confirmed redundant or broken artifacts and repairs concrete boot, persistence,
and verification defects. It does not replace the live lobes with stubs.

## Scope

All 244 original tracked paths received byte comparison and structural/reference
inventory. Python modules received AST parsing and duplicate-definition checks;
the extensionless Python snapshot was also parsed. JSON configuration received
syntax validation. The live execution path was traced from
`run_abin.create_core_systems()` through `Thalamus.process_user_input()`.
`REPOSITORY_AUDIT_INVENTORY.json` accounts for each original path and its disposition.

This is a repository-wide structural audit with targeted behavioral checks, not
proof that every line or optional module works. No PostgreSQL service, camera,
microphone, semantic model download, audio playback device, or desktop GUI was
available for end-to-end verification in this run.

## Removed artifacts

| Path | Evidence and disposition |
| --- | --- |
| `Monday 0.2` | Unreferenced 48,105-line legacy concatenation. Contains pasted prose/output and fails parsing at line 3744. Split source modules remain. |
| `notus_v2.py` | Unimported older SQLite implementation with dozens of copied Notus methods. Current PostgreSQL memory inherits from `notus.py`; the current SQLite adapter is `direct_notus.py`. |
| `Agent smith` | Byte-identical to `.github/agents/my-agent-smith.agent.md`. Canonical agent retained. |
| `.github/agents/my-agent.agent.md` | Same byte-identical agent definition. Canonical agent retained. |
| `integration_test.py` | Obsolete stub flow imports nonexistent `value_goal_management_lobe`. Current pipeline and outage tests remain. |
| First `EnhancedMondayMemorySystem` in `notus.py` | 1,121 lines overwritten by a later class of the same name. Only `__all__` string assignment occurs between definitions. Effective later class AST is unchanged. |

The historical proof logs, fixtures, 3D utilities, migration utility, and distinct
experimental modules were retained. An unimported entrypoint is not automatically
dead code; different implementations are not automatically duplicates.

## Repairs

1. **Optional PostgreSQL driver blocked every boot.** `run_abin.py` imported
   `notus_memory_core` eagerly, which raises when `psycopg2` is absent. This
   prevented both injected SQLite tests and the documented default SQLite
   fallback. PostgreSQL implementation loading now happens only when selecting
   that backend; missing driver reaches the shared durable fallback.
2. **Explicit runtime directory was only partially respected.** Emotion and
   SharedRepresentation used it, while Pattern, lobe learning, and Output's
   speech buffer used the environment default. Independent cores could silently
   share those files. The chosen directory now reaches all three stores. Notus's
   intentional shared identity remains separately configured.
3. **Launchers used incompatible communication.** `launch_abin.py` waited for
   obsolete lobe sockets, and `run_all.sh` launched separate processes whose
   Thalamus instances could not form the direct core. Both now route to
   `run_abin.main`. `launch_abin.py` starts the REPL; its former disconnected GUI
   behavior is deliberately removed.
4. **CI omitted the acceptance suite.** The workflow performed a live memory
   check but never invoked pytest. It now runs both current acceptance files.
5. **The socket-free test did not enforce its claim.** It only imported `socket`.
   The test now fails on socket creation and PostgreSQL-driver import, and new
   tests cover missing-driver restart durability and non-Notus runtime isolation.
6. **README contradicted source behavior.** The blanket claim that all socket code
   was removed was false. Documentation now distinguishes core calls, client
   sockets, legacy code, and the actual supported launch commands.

## Remaining findings

| Area | What remains |
| --- | --- |
| Desktop interfaces | `abin_interface.py` produces its own canned responses. `monday_interface/brain_connector.py` gets an uninitialized singleton rather than calling `create_core_systems`; its emotion/history polling uses the absent `monday_memory` API. These require frontend integration work, not duplicate deletion. |
| Historical configuration | `brain_config.json` still describes socket startup, a machine-specific absolute base path, and an absent `brain_interface.py`. `CONFIG_INDEX.json` names old memory/state paths. The active startup does not consume this file as its launcher contract. Do not treat it as current architecture documentation. |
| Experimental thinking | `continuous_thought_generator.py` and `controlled_thinking.py` are explicitly mock/demo mechanisms and are detached from live boot. `dual_stream_thinking.py` is a separate provider demo. They were retained as distinct experiments. |
| Dormant behavior modules | `experience_processor.py`, `self_reflection.py`, `behavioral_reinforcement.py`, and `notus_helpers.py` are not registered by current boot. Some use old singleton/message expectations; their presence does not prove those capabilities are live. |
| Thought generation | The active autonomous loop still chooses among hand-authored lines, including `_UNRESOLVED_LINES` and memory-snippet templates. Its state machinery is real code, but the output is not evidence of unrestricted generative reasoning. |
| Reasoning breadth | `direct_reasoning.py` seeds three baseline facts and uses lexical/personal-fact extraction. Passing greeting, memory, and selected fact tests does not establish broad question-answering ability. |
| Voice and motor | Voice is labeled a formant/sine synthesis stub; motor can report `no_actuator`. These are explicit capability limits rather than duplicate files to remove. Actual playback and actuators were not verified. |
| Old proof reports | Checked-in `*_before.txt`/`*_after.txt` describe historical runs. The full-bar harness labels belief persistence `noop` even though persistence is now implemented and separately tested. Its 15 passing checks do not prove every claimed subsystem behavior. |
| Legacy Notus code | `notus.py` still carries compatibility/editor/socket behavior beside the memory primitives that active PostgreSQL Notus actually needs. Removing the whole file would break that inheritance chain; a future extraction needs PostgreSQL-backed parity checks. |

## Verification

- Whole pytest discovery: **22 passed** using offline settings and isolated runtime data.
- Full-bar mechanism harness: **15/15 passed**.
- Core emotion harness: **7/7 passed**.
- Unprompted-speech harness: **7/7 passed**.
- Shared chat/REPL Notus identity and belief restart-persistence harnesses: passed
 .
- All retained Python modules parse; all JSON files validate; `bash -n run_all.sh`
  and `git diff --check` pass.

The proof harnesses were rerun after the runtime-routing repair. Both replacement
launchers boot and exit cleanly with EOF from outside the checkout. No tests claim
PostgreSQL or hardware parity without running it.
