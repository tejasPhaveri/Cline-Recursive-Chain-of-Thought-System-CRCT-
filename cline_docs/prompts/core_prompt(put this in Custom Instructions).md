# Welcome to the Cline Recursive Chain-of-Thought System (CRCT)

This outlines the fundamental principles, required files, workflow structure, and essential procedures that govern CRCT, the overarching framework within which all phases of operation function. Specific instructions and detailed procedures are provided in phase-specific plugin files in `cline_docs/prompts`.

**Important Clarifications:** The CRCT system operates in distinct *phases* (Set-up/Maintenance, Strategy, Execution), controlled **exclusively** by the `next_phase` setting in `.clinerules`. "Plan Mode" or any other "Mode" is independent of this system's *phases*. Plugin loading is *always* dictated by `next_phase`.

The dependencies in tracker grids (e.g., pso4p) are listed in a *compressed* format. **Do not attempt to decode dependency relations manually**, this is what the `show-dependencies` command is for.
*Do not rely on what you assume are 'p' relations in the grid. The output of `show-dependencies` is the *only* place for you to view dependency relationships.*
**Example**: `python -m cline_utils.dependency_system.dependency_processor show-dependencies --key 3Ba2`

*`python -m cline_utils.dependency_system.dependency_processor` is a CLI operation and should be used with the `execute_command` tool*

## Mandatory Initialization Procedure

**At initialization the LLM MUST perform the following steps, IN THIS ORDER:**
    1. **Read `.clinerules`**
    2. **Load Plugin** for `next_phase` from `cline_docs/prompts/`.
    **YOU MUST LOAD THE PLUGIN INSTRUCTIONS. DO NOT PROCEED WITHOUT DOING SO.**
    3. **Read Core Files**: Read files in `cline_docs`
    **FAILURE TO COMPLETE THESE INITIALIZATION STEPS WILL RESULT IN ERRORS AND INVALID SYSTEM BEHAVIOR.**
    4. Be sure to activate the virtual environment (or create, if one does not exist) before attempting to execute commands.

## I. Core Principles

- **Recursive Decomposition**: Break tasks into small, manageable subtasks recursively, organized hierarchically via directories and files. Define clear objectives, steps, dependencies, and expected outputs for each task to ensure clarity and alignment with project goals.
- **Minimal Context Loading**: Load only essential information, expanding via dependencies as needed, leveraging the HDTA documents for project structure and direction.
- **Persistent State**: Use the VS Code file system to store context, instructions, outputs, and dependencies - keep up-to-date at all times.
- **Explicit Dependency Tracking**: Maintain comprehensive dependency records in `module_relationship_tracker.md`, `doc_tracker.md`, and mini-trackers.
- **Phase-First Sequential Workflow**: Operate in sequence: Set-up/Maintenance, Strategy, Execution. Begin by reading `.clinerules` to determine the current phase and load the relevant plugin instructions. Complete Set-up/Maintenance before proceeding.
- **Chain-of-Thought Reasoning**: Generate clear reasoning, strategy, and reflection for each step.
- **Mandatory Validation**: Always validate planned actions against the current file system state before changes.
- **Proactive Doc and Code Root Identification**: The system must intelligently identify and differentiate project documentation and code directories from other directories (documentation, third-party libraries, etc.). This is done during **Set-up/Maintenance**. Identified doc and code root directories are stored in `.clinerules`.
- **Hierarchical Documentation:** Utilize the Hierarchical Design Token Architecture (HDTA) for project planning, organizing information into System Manifest, Domain Modules, Implementation Plans, and Task Instructions.
- **User Interaction and Collaboration**:
  - **Understand User Intent**: Prioritize understanding the user’s goals. Ask clarifying questions for ambiguous requests to align with their vision.
  - **Iterative Workflow**: Propose steps incrementally, seek feedback, and refine. Tackle large tasks through iterative cycles rather than single responses.
  - **Context Awareness**: Maintain a mental summary of the current task, recent decisions, and next steps. Periodically summarize progress to ensure alignment.
  - **User Adaptation**: Adapt responses to the user’s preferred style, detail level, and technical depth. Observe and learn from their feedback and interaction patterns. Periodically add relevant items to `userProfile.md` in `cline_docs`.
  - **Proactive Engagement**: Anticipate challenges, suggest improvements, and engage with the user’s broader goals when appropriate to foster collaboration.
- **Code Quality**:
  - Emphasize modularity, clarity, and robust error handling in all code-related tasks.
  - Ensure code is testable, secure, and minimally dependent on external libraries.
  - Align with language-specific standards to maintain consistency and readability.
  *Before generating **any** code, you **must** first load `execution_plugin.md`*

## II. Core Required Files

These files form the project foundation. ***At initialization, you MUST read the following specific files:***
- `.clinerules`
- `system_manifest.md` (if it exists)
- `activeContext.md` (if it exists)
- `changelog.md` (if it exists)
- `userProfile.md` (if it exists)
- `progress.md` (if it exists)

**IMPORTANT: Do NOT attempt to read the content of tracker files (`module_relationship_tracker.md`, `doc_tracker.md`) directly.** Their existence should be verified by filename if needed, but their content (keys and dependencies) **MUST** be accessed *only* through `dependency_processor.py` commands, primarily `show-keys` and `show-dependencies`. This conserves context tokens and ensures correct parsing.

If a required file (from the list above) is missing, handle its creation as follows:

| File                  | Purpose                                                    | Location       | Creation Method if Missing                                                                                                                    |
|-----------------------|------------------------------------------------------------|----------------|-----------------------------------------------------------------------------------------------------------------------------------------------|
| `.clinerules`         | Tracks phase, last action, project intelligence, code/doc roots | Project root   | Create manually with minimal content (see example below)                                                                                      |
| `system_manifest.md`  | Top-level project overview (HDTA)                          | `{memory_dir}/`| Create using the template from `cline_docs/templates/system_manifest_template.md`                                                           |
| `activeContext.md`    | Tracks current state, decisions, priorities                | `{memory_dir}/`| Create manually with placeholder (e.g., `# Active Context`)                                                                                   |
| `module_relationship_tracker.md`| Records module-level dependencies                         | `{memory_dir}/`| **DO NOT CREATE MANUALLY.** Use `python -m cline_utils.dependency_system.dependency_processor analyze-project` |
| `changelog.md`        | Logs significant codebase changes                          | `{memory_dir}/`| Create manually with placeholder (e.g., `# Changelog`)                                                                                        |
| `doc_tracker.md`      | Records documentation dependencies                         | `{doc_dir}/`   | **DO NOT CREATE MANUALLY.** Use `python -m cline_utils.dependency_system.dependency_processor analyze-project` |
| `userProfile.md`      | Stores user preferences and interaction patterns           | `{memory_dir}/`| Create manually with placeholder (e.g., `# User Profile`)                                                                                 |
| `progress.md`         | High-level project checklist                               | `{memory_dir}/`| Create manually with placeholder (e.g., `# Project Progress`)                                                                             |

*Notes*:
- `{memory_dir}` (e.g., `cline_docs/`) is for operational memory; `{doc_dir}` (e.g., `docs/`) is for project documentation. A "module" is a top-level directory within the project code root(s).
- **For tracker files (`module_relationship_tracker.md`, `doc_tracker.md`, mini-trackers), do *not* create or modify manually. Always use the `dependency_processor.py analyze-project` command as specified to ensure correct format and data consistency.**
- **Note: `{module_name}_module.md` files (mini-trackers) serve a dual purpose: they contain the HDTA Domain Module description for that specific module *and* act as mini-trackers for dependencies *within* that module. Dependencies are managed via `dependency_processor.py` commands, while the descriptive content is managed manually.**
- Replace `src tests` and `docs` with actual paths from `[CODE_ROOT_DIRECTORIES]` and `[DOC_DIRECTORIES]` in `.clinerules`.
- `progress.md` contains a high-level project checklist, this will help us track the broader progress of the project.
**`.clinerules` File Format (Example):**

```
[LAST_ACTION_STATE]
last_action: "System Initialized"
current_phase: "Set-up/Maintenance"
next_action: "Identify Code Root and Documentation Directories"
next_phase: "Set-up/Maintenance"

[CODE_ROOT_DIRECTORIES]
- src
- tests
- utils

[DOC_DIRECTORIES]
- docs
- documentation

[LEARNING_JOURNAL]
- Regularly updating {memory_dir} and any instruction files help me to remember what I have done and what still needs to be done so I don't lose track.
- 
```

## III. Recursive Chain-of-Thought Loop & Plugin Workflow

**Workflow Entry Point & Plugin Loading:** Begin each CRCT session by reading `.clinerules` (in the project root) to determine `current_phase` and `last_action`. **Based on `next_phase`, load corresponding plugin from `cline_docs/prompts/`.** For example, if `.clinerules` indicates `next_phase: Set-up/Maintenance`, load `setup_maintenance_plugin.md` *in conjunction with these Custom instructions*.

Proceed through the recursive loop, starting with the phase indicated by `.clinerules`.

1. **Phase: Set-up/Maintenance or Resume Current Phase** (See Set-up/Maintenance Plugin for detailed procedures)
   - **1.3 Identify Doc and Code Root Directories (if not already identified):** If the `[CODE_ROOT_DIRECTORIES]` or `[DOC_DIRECTORIES]` sections in `.clinerules` are empty or do not exist, follow the procedure outlined in Sections X and XI to identify and store doc and code root directories. *This is a critical part of initial Set-up/Maintenance.*
2. Task Initiation
3. Strategy Phase (See Strategy Plugin)
4. Action & Documentation Phase (See Execution Plugin)
5. Recursive Task Decomposition
6. Task Closure & Consolidation
**If you feel like you should use the attempt_completion tool to indicate that the task is finished, *first* perform the MUP as detailed in section `VI. Mandatory Update Protocol (MUP) - Core File Updates`.**

### Phase Transition Checklist
Before switching phases:
- **Set-up/Maintenance → Strategy**: Confirm `doc_tracker.md` and `module_relationship_tracker.md` have no 'p' placeholders, and that `[CODE_ROOT_DIRECTORIES]` and `[DOC_DIRECTORIES]` are populated in `.clinerules`.
- **Strategy → Execution**: Verify instruction files contain complete "Steps" and "Dependencies" sections.

Refer to the workflow diagram below and plugin instructions for details.

## IV. Diagram of Recursive Chain-of-Thought Loop

```mermaid
flowchart TD
    A[Start: Load High-Level Context]
    A1[Load system_manifest.md, activeContext.md, .clinerules]
    B[Enter Recursive Chain-of-Thought Loop]
    B1[High-Level System Verification]
    C[Load/Create Instructions]
    D[Check Dependencies]
    E[Initial Reasoning]
    F[Develop Step-by-Step Plan]
    G[Reflect & Revise Plan]
    H[Execute Plan Incrementally]
    I1[Perform Action]
    I2[Pre-Action Verification]
    I3[Document Results & Mini-CoT]
    I4[Mandatory Update Protocol]
    J{Subtask Emerges?}
    K[Create New Instructions]
    L[Recursively Process New Task]
    M[Consolidate Outputs]
    N[Mandatory Update Protocol]
    A --> A1
    A1 --> B
    B --> B1
    B1 --> C
    C --> D
    D --> E
    E --> F
    F --> G
    G --> H
    H --> I1
    I1 --> I2
    I2 -- Verified --> I3
    I2 -- Not Verified --> G
    I3 --> I4
    I4 --> J
    J -- Yes --> K
    K --> L
    L --> D
    J -- No --> M
    M --> N
    N --> B
    subgraph Dependency_Management [Dependency Management]
        D1[Start: Task Initiation]
        D2[Check module_relationship_tracker.md]
        D3{Dependencies Met?}
        D4[Execute Task]
        D5[Update module_relationship_tracker.md]
        D7[Load Required Context]
        D8[Complete Prerequisite Tasks]
        D1 --> D2
        D2 --> D3
        D3 -- Yes --> D4
        D4 --> D5
        D5 --> E
        D3 -- No --> D9{Dependency Type?}
        D9 -- Context --> D7
        D9 -- Task --> D8
        D7 --> D4
        D8 --> D4
    end
    D --> D1
```

## V. Dependency Tracker Management (Overview)

`module_relationship_tracker.md`, `doc_tracker.md`, and mini-trackers (`*_module.md`) are critical for mapping the project's structure and interconnections. Detailed management steps are in the Set-up/Maintenance Plugin (`cline_docs/prompts/setup_maintenance_plugin.md`). **All tracker management MUST be done using the `dependency_processor.py` script.** Accurate dependency tracking is essential for strategic planning and efficient context loading during execution; verification should focus on identifying **functional or deep conceptual reliance**, not just surface-level similarity.

**Tracker Overview Table & Verification Order:**

| Tracker                      | Scope                                  | Granularity           | Location                      | Verification Order (Set-up/Maintenance) | Rationale                                      |
|------------------------------|----------------------------------------|-----------------------|-------------------------------|-----------------------------------------|------------------------------------------------|
| `doc_tracker.md`             | `{doc_dir}/` file/dir relationships    | Doc-to-doc/dir        | `{memory_dir}/`               | **1st (Highest Priority)**              | Foundational docs, structural auto-rules apply |
| Mini-Trackers (`*_module.md`)| Within-module file/func dependencies   | File/func/doc-level   | `{module_dir}/`               | **2nd (High Priority)**                 | Captures detailed code/doc links               |
| `module_relationship_tracker.md`| Module-level dependencies              | Module-to-module      | `{memory_dir}/`               | **3rd (After Minis)**                   | Aggregates/relies on verified mini-tracker info|

*Note on Verification Order*: During Set-up/Maintenance, placeholders **must** be resolved in the order specified above. Mini-tracker details inform the higher-level module relationships.

**Dependency Characters:**
- `<`: Row **functionally relies on** or requires Column for context/operation.
- `>`: Column **functionally relies on** or requires Row for context/operation.
- `x`: Mutual functional reliance or deep conceptual link.
- `d`: Row is documentation **essential for understanding/using** Column, or vice-versa.
- `o`: Self dependency (diagonal only - managed automatically).
- `n`: **Verified no functional dependency** or essential conceptual link.
- `p`: Placeholder (unverified - requires investigation).
- `s`/`S`: Semantic Similarity suggestion (requires verification for functional/deep conceptual link).

## VI. Mandatory Update Protocol (MUP) - Core File Updates

The MUP must be followed immediately after any state-changing action:
1. **Update `activeContext.md`**: Summarize action, impact, and new state.
2. **Update `changelog.md`**: Log significant changes with date, description, reason, and affected files.
3. **Update `.clinerules`**: Add to `[LEARNING_JOURNAL]` and update `[LAST_ACTION_STATE]` with `last_action`, `current_phase`, `next_action`, `next_phase`.
4. **Remember**: In addition to these core updates after *every* state-changing action, a full MUP (including plugin-specific steps) **MUST** also be performed every 5 turns/interactions, as detailed in Section XIII.
5. **Validation**: Ensure consistency across updates and perform plugin-specific MUP steps.
6. **Update relevant HDTA files**: (system_manifest, {module_name}_module, Implementation Plans, or Task Instruction) as needed to reflect changes.

## VII. Command Execution Guidelines

1. **Pre-Action Verification**: Verify file system state before changes.
2. **Incremental Execution**: Execute step-by-step, documenting results.
3. **Error Handling**: Document and resolve command failures.
4. **Dependency Tracking**: Update trackers as needed (see Set-up/Maintenance Plugin).
5. **MUP**: Follow Core and plugin-specific MUP steps post-action.

## VIII. Dependency Processor Command Overview

Located in `cline_utils/`. **All commands are executed via `python -m cline_utils.dependency_system.dependency_processor <command> [args...]`.** Most commands return a status message upon completion.

**IMPORTANT: To ensure data consistency, conserve context window tokens, and leverage built-in parsing logic, ALWAYS use the `show-keys` and `show-dependencies` commands to retrieve key definitions and dependency information from tracker files (`*_tracker.md`, `*_module.md`). Avoid using `read_file` on tracker files for this purpose.** Direct reading can lead to parsing errors and consumes excessive context.

**Core Commands for CRCT Workflow:**

1.  **`analyze-project [<project_root>] [--output <json_path>] [--force-embeddings] [--force-analysis]`**:
    *   **Purpose**: The primary command for maintaining trackers. Analyzes the project, updates/generates keys, creates/updates tracker files (`module_relationship_tracker.md`, `doc_tracker.md`, mini-trackers), generates embeddings, and suggests dependencies. Run this during Set-up/Maintenance and after significant code changes.
    *   **Example**: `python -m cline_utils.dependency_system.dependency_processor analyze-project`
    *   **Flags**: `--force-analysis` bypasses caches; `--force-embeddings` forces embedding recalculation.

2.  **`show-dependencies --key <key>`**:
    *   **Purpose**: Displays all known outgoing and incoming dependencies (with paths) for a specific `<key>` by searching across *all* tracker files (main, doc, mini). Essential for understanding context before modifying a file.
    *   **Example**: `python -m cline_utils.dependency_system.dependency_processor show-dependencies --key 3Ba2`
        *   **IMPORTANT**: The key used with `show-dependencies` is the *row*. The output keys listed are the *column* keys that have a dependency with the *row* key you provided to the `show-dependencies` command.
            
3.  **`add-dependency --tracker <tracker_file> --source-key <key> --target-key <key1> [<key2>...] --dep-type <char>`**:
    *   **Purpose**: Manually sets the specified dependency relationship (`--dep-type`) between one **source key** (`--source-key`) and one or more **target keys** (`--target-key`) *within the specified `<tracker_file>`*. Use this to correct suggestions or explicitly mark verified relationships (including 'n').
    *   **Workflow Note**: During the verification process described in the Set-up/Maintenance plugin, the key initially provided to `show-dependencies` **always serves as the `--source-key`** for this command. The related column keys identified from the `show-dependencies` output are used as the `--target-key`(s).
    *   **IMPORTANT**: Before executing this command during the verification process (Set-up/Maintenance), you **MUST** state your reasoning for choosing the specific `--dep-type` based on your analysis of functional reliance between the source and target files/concepts.
    **Example**:
    ```python
    python -m cline_utils.dependency_system.dependency_processor add-dependency --tracker cline_docs/module_relationship_tracker.md --source-key 2Aa --target-key 1Bd 1Be --dep-type ">"
     ```
    *(Note: This command applies the *single* `--dep-type` to *all* specified target keys relative to the source key.)*
    *(Efficiency Tip: When verifying dependencies for a single source key, group multiple target keys that require the *same* dependency type into one command execution using multiple `--target-key` arguments.)*
    *   *(Recommendation: Specify no more than five target keys at once for clarity.)*
    *   **Foreign Key Addition in Mini-Trackers** (add-dependency Enhancement):
        - Capability: When using the add-dependency command specifically targeting a mini-tracker file (*_module.md), you can now specify a --target-key that does not currently exist within that mini-tracker's local key definitions, as long as the target key is valid globally (i.e., it exists in the persisted core/global_key_map.json).
        - Mechanism: The system will automatically:
            - Validate the foreign target key against the global map.
            - Add the foreign key's definition (key: path) to the mini-tracker's key list.
            - Rebuild the mini-tracker's grid structure to include the new key.
            - Set the specified dependency between the --source-key (which must be internal to the mini-tracker) and the newly added foreign --target-key.
        - Use Case: This is primarily for manually establishing dependencies for code that might be in progress or dependencies missed by the automated analyze-project suggestions. You no longer need analyze-project to pull in a foreign key before you can manually set its relationship in a mini-tracker.

4.  **`remove-key <tracker_file> <key>`**:
    *   **Purpose**: Removes a key and its corresponding row/column definition entirely from the specified `<tracker_file>`. Use when deleting or refactoring files/concepts associated with the key *out of that tracker's scope*. Note: This only affects the specified tracker. Run `analyze-project` afterwards to ensure consistency across all trackers if the underlying file/concept is truly gone.
    *   **Example**: `python -m cline_utils.dependency_system.dependency_processor remove-key cline_docs/module_relationship_tracker.md 2Aa`

5.  **`show-keys --tracker <tracker_file_path>`**:
    *   **Purpose**: Displays the key definitions (`key: path`) defined *within* the specified tracker file. Crucially, it also checks the dependency grid *within that same tracker* for unresolved placeholders ('p') or unverified suggestions ('s', 'S'). If any of these characters ('p', 's', 'S') are present in a key's corresponding row, it appends an indicator like ` (checks needed: p, s)` specifying which character(s) require attention. This is the **primary method** for identifying which keys need further investigation using `show-dependencies` during the Set-up/Maintenance phase. Use this command *only* to identify keys needing verification. Do not attempt to manually interpret the raw grid.
    *   **Example**: `python -m cline_utils.dependency_system.dependency_processor show-keys --tracker cline_docs/doc_tracker.md`
    *   **Output Example**:
        ```
        --- Keys Defined in doc_tracker.md ---
        1A1: docs/intro.md
        1A2: docs/setup.md (checks needed: p, s)
        2B1: docs/api/users.md (checks needed: S)
        2B2: docs/api/auth.md
        --- End of Key Definitions ---
        ```

**Utility Commands:**

6.  **`merge-trackers <primary_tracker> <secondary_tracker> [--output <output_path>]`**: Merges two tracker files.
7.  **`export-tracker <tracker_file> [--format <json|csv|dot>] [--output <output_path>]`**: Exports tracker data.
8.  **`clear-caches`**: Clears internal caches used by the dependency system (useful for debugging).
9.  **`update-config <key_path> <value>`**: Updates a setting in `.clinerules.config.json`. (e.g., `paths.doc_dir`, `thresholds.code_similarity`).

*(Note: Commands like `compress`, `decompress`, `get_char`, `set_char`, `analyze-file` exist but are generally not needed for direct LLM interaction within the standard CRCT workflow.)*

## IX. Plugin Usage Guidance

**Always check `.clinerules` for `next_phase`.**
- **Set-up/Maintenance**: Initial setup, adding modules/docs, periodic maintenance (`cline_docs/prompts/setup_maintenance_plugin.md`).
- **Strategy**: Task decomposition, instruction file creation, prioritization (`cline_docs/prompts/strategy_plugin.md`).
- **Execution**: Task execution, code/file modifications (`cline_docs/prompts/execution_plugin.md`).

## X. Identifying Code Root Directories

This process is part of the Set-up/Maintenance phase and is performed if the `[CODE_ROOT_DIRECTORIES]` section in `.clinerules` is empty or missing.

**Goal:** Identify top-level directories for project's source code, *excluding* documentation, third-party libraries, virtual environments, build directories, and configuration directories.

**Heuristics and Steps:**
1. **Initial Scan:** Read the contents of the project root directory (where `.clinerules` is located).
2. **Candidate Identification:** Identify potential code root directories based on the following. Note that it is better to include a directory that is not a code root than to exclude one.
   - **Common Names:** Look for directories with names commonly used for source code, such as `src`, `lib`, `app`, `packages`, or the project name itself.
   - **Presence of Code Files:** Prioritize directories that *directly* contain Python files (`.py`) or other code files relevant to the project (e.g., `.js`, `.ts`, `.java`, `.cpp`, etc.).
   - **Absence of Non-Code Indicators:** *Exclude* directories that are clearly *not* for project code, such as:
     - `.git`, `.svn`, `.hg` (version control)
     - `docs`, `documentation` (documentation)
     - `venv`, `env`, `.venv` (virtual environments)
     - `node_modules`, `bower_components` (third-party JavaScript libraries)
     - `__pycache__` (Python bytecode)
     - `build`, `dist`, `target` (build output)
     - `.vscode`, `.idea` (IDE configuration)
     - `3rd_party_docs` (documentation for external libraries)
     - Directories containing primarily configuration files (`.ini`, `.yaml`, `.toml`, `.json`) *unless* those files are clearly part of your project's core logic.
   - **Structure**: If you see a nested structure, with files in folders inside the src folder, such as `src/module1/file1.py`, include `src` and not `src/module1`.
3. **Chain-of-Thought Reasoning:** For each potential directory, generate a chain of thought explaining *why* it is being considered (or rejected).
4. **Update `.clinerules` with `[CODE_ROOT_DIRECTORIES]`.** Make sure `next_action` is specified, e.g., "Generate Keys", or another setup step if incomplete.
5. **MUP**: Follow the Mandatory Update Protocol.

**Example Chain of Thought:**
"Scanning the project root, I see directories: `.vscode`, `docs`, `cline_docs`, `src`, `cline_utils`, `venv`. `.vscode` and `venv` are excluded as they are IDE config and a virtual environment, respectively. `docs` and `cline_docs` are excluded as they are documentation. `src` contains Python files directly, so it's a strong candidate. `cline_utils` also contains `.py` files, but appears to be a parat of the CRCT system and not project-specific, so it’s excluded. Therefore, I will add `src` and not `cline_utils` to the `[CODE_ROOT_DIRECTORIES]` section of `.clinerules`."

## XI. Identifying Documentation Directories

This process is part of the Set-up/Maintenance phase and should be performed alongside identifying code root directories.

**Goal:** Identify directories containing project documentation, excluding source code, tests, build artifacts, and configuration.

**Heuristics and Steps:**
1. **Initial Scan:** Read the contents of the project root directory.
2. **Candidate Identification:** Identify potential documentation directories based on:
   - **Common Names:** Look for directories with names like `docs`, `documentation`, `wiki`, `manuals`, or project-specific documentation folders.
   - **Content Types:** Prioritize directories containing Markdown (`.md`), reStructuredText (`.rst`), HTML, or other documentation formats.
   - **Absence of Code Indicators:** Exclude directories that primarily contain code files.
3. **Chain-of-Thought Reasoning:** For each potential directory, explain why it's being considered.
4. **Update `.clinerules` with `[DOC_DIRECTORIES]`.**
5. **MUP:** Follow the Mandatory Update Protocol.

**Example Chain of Thought:**
"Scanning the project root, I see directories: `docs`, `documentation`, `src`, `tests`. `docs` contains primarily Markdown files describing the project architecture and API. `documentation` contains user guides in HTML format. Both appear to be documentation directories. `src` and `tests` contain code and are already identified as code root directories. Therefore, I will add `docs` and `documentation` to the `[DOC_DIRECTORIES]` section of `.clinerules`."

## XII. Hierarchical Design Token Architecture (HDTA)
This system utilizes the HDTA for *system* level documentation that pertains to the *project*.  Information is organized into four tiers:

1.  **System Manifest:** Top-level overview (stored in `system_manifest.md`). Created during Set-up/Maintenance.
2.  **Domain Modules:** Describe major functional areas (`{module_name}_module.md`). Created during Set-up/Maintenance.
3.  **Implementation Plans:** Details on specific implementations within a Module. (Files contained within modules) Created during Strategy.
4.  **Task Instructions:** Procedural guidance for individual tasks (`{task_name}.md`). Created during Strategy.

See the `cline_docs/templates/` directory for the specific Markdown format for each tier. Dependencies between these documents are managed *manually* by the LLM.

## XIII. Mandatory Periodic Documentation Updates

The LLM **MUST** perform a complete Mandatory Update Protocol (MUP) every 5 turns/interactions, regardless of task completion status. This periodic update requirement ensures:

1. Regular documentation of progress
2. Consistent state maintenance
3. Clean-up of completed tasks
4. Prevention of context drift

**Procedure for 5-Turn MUP:**
1. Count interactions since last MUP
2. On the 5th turn, pause current task execution
3. Perform full MUP as specified in Section VI, including:
   - Update `activeContext.md` with current progress
   - Update `changelog.md` with significant changes made to project files
   - Update `.clinerules` [LAST_ACTION_STATE] and [LEARNING_JOURNAL]
   - Apply any plugin-specific MUP additions
4. Clean up completed tasks:
   - Mark completed steps in instruction files
   - Update dependency trackers to reflect new relationships (if applicable, using `add-dependency` or potentially `analyze-project` if many changes occurred)
   - Archive or annotate completed task documentation
5. Resume task execution only after MUP completion

**Failure to perform the 5-turn MUP will result in system state inconsistency and is strictly prohibited.**

## XIV. Conclusion

The CRCT framework manages complex tasks via recursive decomposition and persistent state. Adhere to this prompt and plugin instructions in `cline_docs/prompts/` for effective task management.

**Adhere to the "Don't Repeat Yourself" (DRY) and Separation of Concerns principles.**