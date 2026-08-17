# New System Implementation Plan

## 1) Goal Clarification

### Problem
Monday has multiple legacy and experimental modules, while the direct-core path is the stable runtime path. A dedicated orchestration layer is needed to make system startup, runtime checks, and operational visibility consistent and safer.

### System to build
Build a **Core Orchestration System** that manages direct-core lifecycle: startup validation, lobe registration checks, health monitoring, and controlled shutdown.

### Primary users
- Repository maintainers extending core behavior
- Developers running local direct-core sessions
- Test/QA contributors validating direct-core reliability

### Success criteria
- Direct-core starts with deterministic preflight validation
- All required lobes are registered and healthy before request handling
- Health status is observable in one place
- Failures provide actionable diagnostics and safe fallback behavior

## 2) Core Requirements

### Must-have features
1. **Preflight validation**
   - Validate required configuration files and runtime directory availability
   - Validate mandatory direct-core components are importable
2. **Startup orchestration**
   - Start required core systems in a strict order
   - Block until required lobe registrations are confirmed
3. **Health and readiness**
   - Continuous lobe health snapshot
   - Ready/not-ready state exposed to callers
4. **Failure handling**
   - Structured error paths for startup and runtime failures
   - Graceful shutdown sequence on unrecoverable failures
5. **Operational reporting**
   - Standardized status summary (startup result, healthy/unhealthy lobes, last failure)

### Constraints
- Must preserve direct-call architecture (no sockets)
- Must remain compatible with `run_abin.py` direct-core path
- Must not require PostgreSQL or GUI for baseline runtime
- Must keep runtime mutable state outside the repository

### Integrations
- `thalamus.py` for lobe registration and health visibility
- `run_abin.py` for direct-core creation and wiring
- Runtime state handling defined in `runtime_paths.py`

## 3) Architecture

### Proposed components
- **Orchestrator module**: lifecycle controller for startup/readiness/shutdown
- **Preflight checker**: configuration and environment validation
- **Readiness gate**: verifies required lobe registration and health
- **Health reporter**: normalized health/status output

### Data model (minimum)
- Required lobes list
- Lobe status map: `registered`, `healthy`, `last_seen`
- Startup result: `success`, `failure_reason`, `timestamp`
- Runtime status: `ready`, `unhealthy_lobes`, `last_error`

### API surface (internal)
- `run_preflight()`
- `start_core()`
- `wait_until_ready(timeout)`
- `get_system_status()`
- `shutdown_core(reason)`

## 4) Phased Delivery

### Phase 1 (MVP)
- Add orchestrator skeleton and preflight checks
- Wire orchestrator into direct-core startup path
- Enforce readiness gate before request processing
- Add baseline unit tests for startup and readiness states

### Phase 2
- Add periodic health polling and status snapshots
- Add structured failure categorization and recovery hooks
- Expand test coverage for partial lobe failure scenarios

### Phase 3
- Add richer observability output for local ops/debug use
- Tighten integration tests around startup/shutdown idempotency
- Document operator workflow for diagnosing unhealthy core states

## 5) Quality Gates

### Testing
- Unit tests: preflight validation, readiness gating, status reporting
- Integration tests: startup success path, startup failure path, controlled shutdown
- Regression tests: preserve existing direct core prompted pipeline behavior

### Monitoring and diagnostics
- Structured status payload for every startup attempt
- Standard unhealthy-lobe reporting format
- Last-error capture for rapid debugging

### Security
- No secrets in repository files or logs
- Runtime state remains in private runtime directory
- Validate file paths and config inputs before use

### Deployment workflow
- Local verification with existing pytest suite
- Merge only when orchestrator tests and existing direct-core tests pass
- Keep rollout behind direct-core startup entrypoint to limit blast radius
