# CRCT Development Guide

<!-- ────────────────────────────────────────────────────────────── -->
## 1 · Project snapshot
Cline Recursive Chain-of-Thought (**CRCT**) is an AI-assisted workflow that
recursively decomposes large coding tasks into bite-size, verifiable steps.
The system currently supports three phases:

| Phase       | Entrypoint                            | Purpose                               |
|-------------|---------------------------------------|---------------------------------------|
| Strategy    | `strategy/plan_generator.py`          | Break high-level tasks into a plan    |
| Execution   | `execution/execute_plan.py::run()`    | Carry out each plan step              |
| Cleanup     | `cleanup/post_process.py`             | Format, doc, and final checks         |

> **Active dev branch:** `execution-refactor`

---

## 2 · Execution-phase architecture cheatsheet
| Component | Path | Notes |
|-----------|------|-------|
| **Run loop** | `execution/execute_plan.py` | Calls tool functions then verifies |
| **Utilities** | `cline_utils/__init__.py` | Common helpers |
| **Cache (NEW)** | `cline_utils/cache.py` | In-memory LRU cache (phase 1) |
| **Tool wrappers** | `tools/*.py` | `read_file`, `show_dependencies`, etc. |

---

## 3 · How to run & test
```bash
# install and test (requires Poetry)
poetry install          # install deps
poetry run pytest -q    # run unit tests
