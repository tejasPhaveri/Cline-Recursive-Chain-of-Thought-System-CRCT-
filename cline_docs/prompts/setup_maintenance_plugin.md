# **Cline Recursive Chain-of-Thought System (CRCT) - Set-up/Maintenance Plugin**

**This Plugin provides detailed instructions and procedures for the Set-up/Maintenance phase of the CRCT system. It should be used in conjunction with the Core System Prompt.**

## I. Entering and Exiting Set-up/Maintenance Phase

**Entering Set-up/Maintenance Phase:**
1. **Initial State**: Start here for new projects or if `.clinerules` shows `current_phase: "Set-up/Maintenance"`.
2. **`.clinerules` Check**: Always read `.clinerules` first. If `[LAST_ACTION_STATE]` indicates "Set-up/Maintenance", proceed with these instructions.
3. **New Project**: If `.clinerules` is missing/empty, assume this phase and initialize core files.

**Exiting Set-up/Maintenance Phase:**
1. **Completion Criteria:**
   - All core files exist and are initialized.
   - `doc_tracker.md` is populated (no 'p' placeholders).
   - `module_relationship_tracker.md` is populated (no 'p' placeholders).
   - `system_manifest.md` is created.
   - Templates in `cline_docs/templates/` are used to create the necessary files and instructions.   
   - Mini-trackers are created/populated as needed.
2. **`.clinerules` Update (MUP):**
   ```
   last_action: "Completed Set-up/Maintenance Phase"
   current_phase: "Set-up/Maintenance"
   next_action: "Phase Complete - User Action Required"
   next_phase: "Strategy"
   ```
3. **User Action**: After updating `.clinerules`, pause for user to trigger the next session (e.g., reset context in VS Code). See Core System Prompt, Section III for a phase transition checklist.

## II. Initializing Core Required Files

**Action**: Ensure all core files exist, creating them if missing as specified.

**Procedure:**
1.  **Check for Existence**: Check if each core file (`.clinerules`, `system_manifest.md`, `activeContext.md`, `module_relationship_tracker.md`, `changelog.md`, `doc_tracker.md`) exists.
2.  **Identify Code and Documentation Directories**: If `[CODE_ROOT_DIRECTORIES]` or `[DOC_DIRECTORIES]` in `.clinerules` are empty or missing, follow the procedures in Core Prompt Sections X and XI to identify and populate these sections.
3.  **Create Missing Files:**
    *   For `.clinerules`, `activeContext.md`, `changelog.md`: Use `write_to_file` to create manually with minimal content.
    *   For `system_manifest.md`: Use `write_to_file` to create it, then populate it using the template from `cline_docs/templates/system_manifest_template.md`.
    *   For tracker files (`module_relationship_tracker.md`, `doc_tracker.md`): Run `analyze-project`. This command will create or update the trackers based on project analysis.
     ```
     python -m cline_utils.dependency_system.dependency_processor analyze-project
     ```
    *(Mini-trackers in module directories are also created/updated by `analyze-project`)*

   - **Important**: Do not manually create tracker files. **Always** use `analyze-project` for initial setup and subsequent updates to ensure proper structure, key generation, and data consistency.
   - Example Initial `.clinerules`:
     ```
     [LAST_ACTION_STATE]
     last_action: "System Initialized"
     current_phase: "Set-up/Maintenance"
     next_action: "Initialize Core Files"
     next_phase: "Set-up/Maintenance"
     ```
3. **MUP**: Follow Core Prompt MUP after creating files.

## III. Analyzing and Verifying Tracker Dependencies (Ordered Workflow)

**Objective**: Ensure trackers accurately reflect project dependencies by resolving placeholders ('p') and verifying suggestions ('s', 'S'). **This process MUST follow a specific order:** `doc_tracker.md` first, then all Mini-Trackers, and finally `module_relationship_tracker.md`. This order is crucial because Mini-Trackers capture cross-directory dependencies within modules, which are essential for accurately determining the higher-level module-to-module relationships in `module_relationship_tracker.md`.

**IMPORTANT**:
*   **All tracker modifications MUST use `dependency_processor.py` commands.**
*   **Do NOT read tracker files directly** for dependency information; use `show-keys` and `show-dependencies`.
*   Run `analyze-project` *before* starting this verification process if significant code/doc changes have occurred or if trackers are potentially outdated.

**Procedure:**

1.  **Run Project Analysis (Initial & Updates)**:
    *   Use `analyze-project` to automatically generate/update keys, analyze files, suggest dependencies, and update *all* trackers (`module_relationship_tracker.md`, `doc_tracker.md`, and mini-trackers). This command creates trackers if they don't exist and populates/updates the grid.
    ```bash
    python -m cline_utils.dependency_system.dependency_processor analyze-project
    ```
    *   *(Optional: Add `--force-analysis` or `--force-embeddings` if needed)*.
    *   **Review logs (`debug.txt`, `suggestions.log`)** for analysis details and suggested changes, but prioritize the workflow below for verification.

2.  **Identify Keys Needing Verification**:
    *   For each tracker:
        *   Run `python -m cline_utils.dependency_system.dependency_processor show-keys --tracker <tracker_file_path>`
        *   Examine the output. Identify all lines ending with an indicator like ` (checks needed: ...)`. This indicator specifies which unresolved characters ('p' - placeholder, 's' - weak suggestion, 'S' - strong suggestion) were found in that key's dependency row *within this specific tracker*. Any key with this indicator requires further investigation.
        *   Create a list of these keys (e.g., `['1A2', '3Bc1']`) for the current tracker that need verification.

3.  **Verify Placeholders ('p') and Suggestions ('s', 'S') for Identified Keys**:
    *   Iterate through the list of keys identified in the previous step for the *current tracker*.
    *   For each `key_string` in the list:
        *   **Retrieve dependency relationships with `show-dependencies`**: Run `python -m cline_utils.dependency_system.dependency_processor show-dependencies --key <key_string>` for this key. This command searches *across all trackers* to show *all* known relationships involving this key (both incoming and outgoing), providing crucial context.
        *   **Analyze Output & Plan Efficient Reading**: Review the `show-dependencies` output. Identify target keys associated with the current `source_key` *in this tracker* that show 'p', 's', or 'S' relationships. **To improve efficiency, plan to read the source file (`<key_string>`) and *multiple* relevant target files together in the next step.** If several target files reside in the same directory, ask the user if they can provide the directory contents using a command like `@add folder {folder_name}` to load them all at once. Always be mindful that you are efficiently using available context and maximizing the use of every API call.
        *   **Examine Source Files (Batch Preferred)**: Use `read_file` to examine the content of the source file (`<key_string>`) AND the batch of relevant target files identified in the previous step. If the user provided folder contents, analyze those.
        *   **Determine Correct Relationship (CRITICAL STEP)**: Based on your analysis of the file contents, determine the **true underlying relationship**.
            *   **Go Beyond Surface Similarity**: The 's' and 'S' suggestions from `analyze-project` are based on semantic similarity, which might only indicate related topics, not necessarily a *dependency* needed for operation or understanding.
            *   **Focus on Functional Reliance**: Ask:
                *   Does the code in the *row file* directly **import, call, or inherit from** code in the *column file*? (Leads to '<' or 'x').
                *   Does the code in the *column file* directly **import, call, or inherit from** code in the *row file*? (Leads to '>' or 'x').
                *   Does the documentation in the *row file* **require information or definitions** present *only* in the *column file* to be complete or accurate? (Leads to '<' or 'd').
                *   Is the *row file* **essential documentation** for understanding or implementing the concepts/code in the *column file*? (Leads to 'd' or potentially '>').
                *   Is there a **deep, direct conceptual link** where understanding or modifying one file *necessitates* understanding the other, even without direct code imports? (Consider '<', '>', 'x', or 'd' based on the nature of the link).
            *   **Purpose of Dependencies**: Remember, these verified dependencies guide the **Strategy phase** (determining task order) and the **Execution phase** (loading minimal necessary context). A dependency should mean "You *need* to consider/load the related file to work effectively on this one."
            *   **Assign 'n' if No True Dependency**: If the relationship is merely thematic, uses similar terms, or is indirect, assign 'n' (verified no dependency). *It is better to mark 'n' than to create a weak dependency.*
            *   **State Reasoning (MANDATORY)**: Before proceeding to the next step (`add-dependency`), you **MUST** clearly state your reasoning for the chosen dependency character (`<`, `>`, `x`, `d`, or `n`) for each specific relationship you intend to set, based on your *direct* analysis of the source files and the functional reliance criteria outlined above.
        *   **Correct/Confirm Dependencies**: After stating your reasoning, use `python -m cline_utils.dependency_system.dependency_processor add-dependency --tracker --source-key --target-key` command, targeting the *current tracker file* you are verifying. **Crucially, the `<key_string>` (the key you initially ran `show-dependencies` on) is ALWAYS the `--source-key` for this `add-dependency` operation.**
            *   The keys identified from `show-dependencies` output (the column keys whose relationship you are verifying) become the `--target-key` values. Set the correct dependency character between the row key (`--source-key <key_string>`) and the specific column key(s) (`--target-key <column_key_1> [<column_key_2>...]`) you just verified. You can update multiple target relationships for the *same source key* in one command if they share the same new dependency type.
          ```bash
          # Example: Set '>' from 1A2 (source) to 2B1 (target) in doc_tracker.md
          # Reasoning: File associated with 1A2 (docs/setup.md) details setup steps required BEFORE using the API described in 2B1 (docs/api/users.md). Thus, 2B1 depends on 1A2.
          python -m cline_utils.dependency_system.dependency_processor add-dependency --tracker cline_docs/doc_tracker.md --source-key 1A2 --target-key 2B1 --dep-type ">"

          # Example: Set 'n' from 1A2 (source) to 3C1 and 3C2 (targets) in doc_tracker.md
          # Reasoning: Files 3C1 and 3C2 are unrelated examples and have no functional dependency on the setup guide 1A2.
          python -m cline_utils.dependency_system.dependency_processor add-dependency --tracker cline_docs/doc_tracker.md --source-key 1A2 --target-key 3C1 3C2 --dep-type "n"
          ```
          (Focus on batching targets for the *same source key* and *same dependency type* per command.)
          *(Recommendation: Handle only a few target keys per `add-dependency` command for clarity.)*

4.  **Iterate and Complete**:
    *   Repeat Step 3 for all keys identified with `(placeholders present)` in the current tracker.
    *   Run `show-keys --tracker <tracker_file_path>` again to confirm no `(placeholders present)` remain for that tracker.
    *   Repeat Steps 2-4 for all relevant tracker files. Prioritize clearing placeholders in `doc_tracker.md` and mini-trackers before `module_relationship_tracker.md`.

5.  **MUP**: Apply Core MUP and Section VII additions after each significant verification session and upon completion of tracker verification.

## IV. Dependency Tracker Management (Details)
*(Dependency character definitions are in the Core System Prompt, Section V)*

### IV.1 Hierarchical Key System
- **Purpose**: Encodes hierarchy in trackers.
- **Structure**: Tier (number), Directory (uppercase), Subdirectory (lowercase), File (number).
- **Examples**: `1A` (top-level dir 'A'), `1A1` (first file in 'A'), `2Ba3` (third file in subdir 'a' of 'B').

### IV.3 Grid Format and X-Axis Header
- **X-Axis Header**: "X " followed by column keys.
- **Dependency Rows**: Row key, " = ", compressed string (RLE, excluding 'o').

### IV.4 Dependency Processor Commands

*(Refer to the Core System Prompt, Section VIII, for a more comprehensive list and detailed description of common `dependency_processor.py` commands.)*

**Key commands for configuration and setup in this phase include:**

-   **`update-config <key_path> <value>`**: Updates a configuration setting in `.clinerules.config.json`.
    -   *Example*: `python -m cline_utils.dependency_system.dependency_processor update-config thresholds.code_similarity 0.8`
    -   *Example*: `python -m cline_utils.dependency_system.dependency_processor update-config models.doc_model_name all-MiniLM-L6-v2`
    -   This command can be used to adjust various settings, including embedding model names (`models.doc_model_name`, `models.code_model_name`), similarity thresholds (`thresholds.doc_similarity`, `thresholds.code_similarity`), and compute device (`compute.embedding_device`).

-   **`reset-config`**: Resets all configuration settings in `.clinerules.config.json` to their default values.
    -   *Example*: `python -m cline_utils.dependency_system.dependency_processor reset-config`

*Note: Key commands used in this phase include `analyze-project`, `show-dependencies`, `add-dependency`, `update-config`, `reset-config`, and `remove-key` as detailed in the procedures above.*

### IV.5 Set-up/Maintenance Dependency Workflow
```mermaid
graph TD
    A[Start Set-up/Maintenance] --> B(Run analyze-project?);
    B -- Yes --> C[Execute analyze-project];
    B -- No --> D[Stage 1: Verify doc_tracker.md];
    C --> D;

    subgraph Verify_doc_tracker [Stage 1: doc_tracker.md]
        D1[Use show-keys --tracker doc_tracker.md] --> D2{Checks Needed<br>Indicated?};
        D2 -- Yes --> D3[Identify Key with<br>'(checks needed: ...)'<br>indicator];
        D3 --> D4(Run show-dependencies --key [key]);
        D4 --> D5(Plan Reading / Suggest @add folder);
        D5 --> D6(Read Source + Target Files);
        D6 --> D7(Determine Relationships);
        D7 --> D8(State Reasoning);
        D8 --> D9(Use<br>add-dependency<br>--tracker [current tracker]<br>--source-key [key]<br>--target-key [...]<br>--dep-type [...]);
        D9 --> D1;
        D2 -- No --> D10[doc_tracker Verified];
    end

    D --> Verify_doc_tracker;
    D10 --> E[MUP after Stage 1];

    E --> F[Stage 2: Find & Verify Mini-Trackers];
    subgraph Find_Verify_Minis [Stage 2: Mini-Trackers]
        F1[Identify Code Roots from .clinerules] --> F2[Scan Code Roots Recursively];
        F2 --> F3[Find *_module.md Files];
        F3 --> F4[Compile List of Mini-Tracker Paths];
        F4 --> F5{Any Mini-Trackers Found?};
        F5 -- Yes --> F6[Select Next Mini-Tracker];
        F6 --> F7[Use show-keys --tracker <mini_tracker>];
        F7 --> F8{Checks Needed<br>Indicated?};
        F8 -- Yes --> F9[Identify Key];
        F9 --> F10(Run show-dependencies --key [key]);
        F10 --> F11(Plan Reading / Suggest @add folder);
        F11 --> F12(Read Source + Target Files);
        F12 --> F13(Determine Relationships);
        F13 --> F14(State Reasoning);
        F14 --> F15(Use add-dependency --tracker <mini_tracker>);
        F15 --> F7;
        F8 -- No --> F16{All Mini-Trackers Checked?};
        F16 -- No --> F6;
        F16 -- Yes --> F17[Mini-Trackers Verified];
        F5 -- No --> F17; // Skip if no minis found
    end

    F --> Find_Verify_Minis;
    F17 --> G[MUP after Stage 2];

    G --> H[Stage 3: Verify module_relationship_tracker.md];
    subgraph Verify_main_tracker [Stage 3: module_relationship_tracker.md]
        H1[Use show-keys --tracker module_relationship_tracker.md] --> H2{Checks Needed<br>Indicated?};
        H2 -- Yes --> H3[Identify Key];
        H3 --> H4(Run show-dependencies --key [key]);
        H4 --> H5(Plan Reading / Use Mini-Tracker Context);
        H5 --> H6(Read Source + Target Module Docs);
        H6 --> H7(Determine Relationships);
        H7 --> H8(State Reasoning);
        H8 --> H9(Use add-dependency --tracker module_relationship_tracker.md);
        H9 --> H1;
        H2 -- No --> H10[Main Tracker Verified];
    end

    H --> Verify_main_tracker;
    H10 --> I[MUP after Stage 3];
    I --> J[End Verification Process];

    style Verify_doc_tracker fill:#e6f7ff,stroke:#91d5ff
    style Find_Verify_Minis fill:#f6ffed,stroke:#b7eb8f
    style Verify_main_tracker fill:#fffbe6,stroke:#ffe58f

## V. Populating Mini-Trackers

**Objective**: Populate mini-trackers in `*_module.md` files located in the code directories.

**Procedure:**

**Find and Verify Mini-Trackers**
1.  **Identify Mini-Tracker Files**:
    *   **Goal**: Locate all `*_module.md` files within the project's code directories.
    *   **Get Code Roots**: Read the `[CODE_ROOT_DIRECTORIES]` list from `.clinerules`.
    *   **Scan Directories**: For each code root directory, recursively scan its contents.
    *   **Pattern Matching**: Identify files matching the pattern `{dirname}_module.md`. For example, in a directory named `user_auth`, look for `user_auth_module.md`.
    *   **Verification**: Ensure the `{dirname}` part of the filename exactly matches the name of the directory containing the file.
    *   **Create List**: Compile a list of the full, normalized paths to all valid mini-tracker files found. If none are found, and code roots exist, inform the user that `analyze-project` might need to be run to generate them.
2. **Instruction File Check:**
   - If `*_module.md` is missing:
     - Run `dependency_processor` with the analyze-project command.      
   - If it exists, proceed to Step 3.
3. **Suggest and Validate**: See **Section IV.5** for example commands. Adapt `--tracker` and keys accordingly.
5. **Iterate and Complete**: Repeat until populated.
6. **MUP**: Apply Core MUP and Section VI additions.

## VI. Set-up/Maintenance Plugin - MUP Additions

After Core MUP steps:
1. **Update `system_manifest.md`**: Ensure it's up to date with any changes made to the project.
2. **Update `.clinerules` [LAST_ACTION_STATE]:**

    - Example after `doc_tracker.md`:

    ```
    [LAST_ACTION_STATE]
    last_action: "Populated doc_tracker.md"
    current_phase: "Set-up/Maintenance"
    next_action: "Populate {dirname}_module.md"
    next_phase: "Set-up/Maintenance"
    ```
