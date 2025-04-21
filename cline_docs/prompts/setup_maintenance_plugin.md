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

## III. Analyzing and Verifying Tracker Dependencies

**Objective**: Ensure trackers accurately reflect project dependencies, removing 'p' placeholders. **All tracker modifications MUST use `dependency_processor.py` commands.** **Do NOT read tracker files directly.**

**Procedure:**

1.  **Run Project Analysis (Initial & Updates)**:
    *   Use `analyze-project` to automatically generate/update keys, analyze files, suggest dependencies, and update *all* trackers (`module_relationship_tracker.md`, `doc_tracker.md`, and mini-trackers). This command creates trackers if they don't exist and populates/updates the grid.
    ```bash
    python -m cline_utils.dependency_system.dependency_processor analyze-project
    ```
    *   *(Optional: Add `--force-analysis` or `--force-embeddings` if needed)*.
    *   **Review logs (`debug.txt`, `suggestions.log`)** for analysis details and suggested changes, but prioritize the workflow below for verification.

2.  **Identify Keys Needing Verification (Using `show-keys`)**:
    *   For each primary tracker (`module_relationship_tracker.md`, `doc_tracker.md`) and relevant mini-trackers:
        *   Run the `show-keys` command.
        ```bash
        python -m cline_utils.dependency_system.dependency_processor show-keys --tracker <tracker_file_path>
        ```
        *   Examine the output. Identify all lines ending with ` (placeholders present)`. These indicate keys defined *in this tracker* whose dependency row *in this tracker's grid* contains unverified 'p' relationships.
        *   Create a list of these keys (e.g., `['1A2', '3Bc1']`) for the current tracker.

3.  **Verify Placeholders ('p') and Suggestions ('s', 'S') for Identified Keys**:
    *   Iterate through the list of keys identified in the previous step for the *current tracker*.
    *   For each `key_string` in the list:
        *   **Get Context with `show-dependencies`**: Run `show-dependencies` for this key. This command searches *across all trackers* to show *all* known relationships involving this key (both incoming and outgoing), providing crucial context.
          ```bash
          python -m cline_utils.dependency_system.dependency_processor show-dependencies --key <key_string>
          ```
        *   **Analyze Output**: Review the output of `show-dependencies`. Pay attention to relationships marked as 'p', 's', or 'S' where `<key_string>` is the row key. Note the *column keys* and their associated *paths* involved in these 'p', 's', or 'S' relationships.
        *   **Examine Source Files**: Use `read_file` to examine the content of the file associated with `<key_string>` (the row) AND the files associated with the relevant *column keys* identified in the previous step.
        *   **Determine Correct Relationship (CRITICAL STEP)**: Based on your analysis of the file contents, determine the **true underlying relationship**.
            *   **Go Beyond Surface Similarity**: The 's' and 'S' suggestions from `analyze-project` are based on semantic similarity, which might only indicate related topics, not necessarily a *dependency* needed for operation or understanding.
            *   **Focus on Functional Reliance**: Ask:
                *   Does the code in the *row file* directly **import, call, or inherit from** code in the *column file*? (Leads to '<' or 'x').
                *   Does the code in the *column file* directly **import, call, or inherit from** code in the *row file*? (Leads to '>' or 'x').
                *   Does the documentation in the *row file* **require information or definitions** present *only* in the *column file* to be complete or accurate? (Leads to '<' or 'd').
                *   Is the *row file* **essential documentation** for understanding or implementing the concepts/code in the *column file*? (Leads to 'd' or potentially '>').
                *   Is there a **deep, direct conceptual link** where understanding or modifying one file *necessitates* understanding the other, even without direct code imports? (Consider '<', '>', 'x', or 'd' based on the nature of the link).
            *   **Purpose of Dependencies**: Remember, these verified dependencies guide the **Strategy phase** (determining task order) and the **Execution phase** (loading minimal necessary context). A dependency should mean "You *need* to consider/load the related file to work effectively on this one."
            *   **Assign 'n' if No True Dependency**: If the relationship is merely thematic, uses similar terms, or is indirect, assign 'n' (verified no dependency). **It is better to mark 'n' than to create a weak dependency.**
            *   **Record Verification**: If you are confirming or changing an 's'/'S' suggestion, briefly note the *reasoning* for the final dependency type (or 'n') in the `.clinerules [LEARNING_JOURNAL]`. Example: "Verified `1A2 -> 2B1` as '>' because 1A2's class inherits from a base class in 2B1, overriding initial 'S' suggestion."
        *   **Correct/Confirm Dependencies with `add-dependency`**: Use the `add-dependency` command, targeting the *current tracker file* you are verifying. Set the correct dependency character between the row key (`--source-key <key_string>`) and the specific column key(s) (`--target-key <column_key_1> [<column_key_2>...]`) you just verified. You can update multiple target relationships for the *same source key* in one command if they share the same new dependency type.
          ```bash
          # Example: Set '>' from 1A2 to 2B1 in doc_tracker.md
          python -m cline_utils.dependency_system.dependency_processor add-dependency --tracker cline_docs/doc_tracker.md --source-key 1A2 --target-key 2B1 --dep-type ">"

          # Example: Set 'n' from 1A2 to 3C1 and 3C2 in doc_tracker.md
          python -m cline_utils.dependency_system.dependency_processor add-dependency --tracker cline_docs/doc_tracker.md --source-key 1A2 --target-key 3C1 3C2 --dep-type "n"
          ```
          *(Recommendation: Handle only a few target keys per `add-dependency` command for clarity.)*

4.  **Iterate and Complete**:
    *   Repeat Step 3 for all keys identified with `(placeholders present)` in the current tracker.
    *   Run `show-keys --tracker <tracker_file_path>` again to confirm no `(placeholders present)` remain for that tracker.
    *   Repeat Steps 2-4 for all relevant tracker files. Prioritize clearing placeholders in `doc_tracker.md` and `module_relationship_tracker.md` before moving to the Strategy phase.

5.  **MUP**: Apply Core MUP and Section VII additions after each significant verification session (e.g., after clearing placeholders for one tracker) and upon completion of primary tracker verification.

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
flowchart TD
    A[Start Set-up/Maintenance] --> B(Run<br>analyze-project);
    B --> C{Review Logs (Optional)};
    C --> D(Select Tracker File);
    D --> E(Use<br>show-keys --tracker);
    E --> F{Placeholders Indicated?};
    F -- Yes --> G[Identify Key with '(placeholders present)'];
    G --> H(Use<br>show-dependencies --key [key]);
    H --> I(Read Related Source Files<br>Based on show-dependencies output);
    I --> J{Determine Correct<br>Character(s)};
    J --> K(Use<br>add-dependency<br>--tracker [current tracker]<br>--source-key [key]<br>--target-key [...]<br>--dep-type [...]);
    K --> L(Record s/S Verification<br>in .clinerules [LEARNING_JOURNAL]);
    L --> E;  // Check keys again for the *same* tracker
    F -- No --> M{All Trackers Checked?};
    M -- No --> D; // Select next tracker
    M -- Yes --> N[Trackers Verified];
    N --> O[End Set-up/Maintenance Phase];

    subgraph Verification Loop for One Key
        direction LR
        H; I; J; K; L;
    end
```

## V. Populating Mini-Trackers

**Objective**: Populate mini-trackers in `*_module.md` files located in the code directories.

**Procedure:**
1. **Identify Modules**: Use `module_relationship_tracker.md` directories.
2. **Instruction File Check:**
   - If `*_module.md` is missing:
     - Run `dependency_processor` with the analyze-project command.      
   - If it exists, proceed to Step 3.
3. **Suggest and Validate**: See **Section IV.5** for example commands. Adapt `--tracker` and keys accordingly.
5. **Iterate and Complete**: Repeat until populated.
6. **MUP**: Apply Core MUP and Section VI additions.

## VI. Set-up/Maintenance Plugin - MUP Additions

After Core MUP steps:
1. **Update `system_manifest.md`**: Ensure it's initialized using the template.
2. **Update `module_relationship_tracker.md`**: Save changes from commands.
3. **Update `doc_tracker.md`**: Save changes.
4. **Update Mini-Trackers**: Save changes.
5. **Update `.clinerules` [LAST_ACTION_STATE]:**

    - Example after `doc_tracker.md`:

    ```
    [LAST_ACTION_STATE]
    last_action: "Populated doc_tracker.md"
    current_phase: "Set-up/Maintenance"
    next_action: "Populate module_relationship_tracker.md"
    next_phase: "Set-up/Maintenance"
    ```
