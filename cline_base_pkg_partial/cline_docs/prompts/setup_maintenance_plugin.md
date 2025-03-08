# **Cline Recursive Chain-of-Thought System (CRCT) - Set-up/Maintenance Plugin**

**This Plugin provides detailed instructions and procedures for the Set-up/Maintenance phase of the CRCT system. It should be used in conjunction with the Core System Prompt.**

---

## I. Entering and Exiting Set-up/Maintenance Phase

**Entering Set-up/Maintenance Phase:**

1. **Initial State**: Start here for new projects or if `.clinerules` shows `current_phase: "Set-up/Maintenance"`.

2. **`.clinerules` Check**: Always read `.clinerules` first. If `[LAST_ACTION_STATE]` indicates "Set-up/Maintenance", proceed with these instructions.

3. **New Project**: If `.clinerules` is missing/empty, assume this phase and initialize core files.

**Exiting Set-up/Maintenance Phase:**

1. **Completion Criteria**:

* All core files exist and are initialized.

* `doc_tracker.md` is populated (no 'p' placeholders).

* `dependency_tracker.md` is populated (no 'p' placeholders).

* Mini-trackers are created/populated as needed.

2. **`.clinerules` Update (MUP)**:

    ```
    last_action: "Completed Set-up/Maintenance Phase"
    current_phase: "Set-up/Maintenance"
    next_action: "Phase Complete - User Action Required"
    next_phase: "Strategy"
    ```

3. **User Action**: After updating `.clinerules`, pause for user to trigger the next session (e.g., reset context in VS Code). See Core System Prompt, Section III for a phase transition checklist.

---

## II. Initializing Core Required Files

**Action**: Ensure all core files exist, creating them if missing as specified.

**Procedure**:

1. **Check for Existence**: Check if each file (`.clinerules`, `projectbrief.md`, `productContext.md`, `activeContext.md`, `dependency_tracker.md`, `changelog.md`, `doc_tracker.md`) exists.

2. **Create Missing Files**:

* For `.clinerules`, `projectbrief.md`, `productContext.md`, `activeContext.md`, `changelog.md`: Use `write_to_file` to create manually with minimal content (e.g., `# Project Brief\n\n[Describe mission here]` for `projectbrief.md`).

* For `dependency_tracker.md`: Run:

```
python -m cline_utils.dependency_system.dependency_processor generate-keys --root_paths  --output {memory_dir}/dependency_tracker.md --tracker_type main
```

        *Replace `<code_root_dir(s)>` with the actual paths to your **code root directories** as identified in **Section XI of the Core System Prompt**. `{memory_dir}` is a placeholder for the memory directory (e.g., `cline_docs/`), as defined in the Core System Prompt.*  For multiple directories, use a space separated list i.e. "src tests".
    *   For `doc_tracker.md`: Run:

```
python -m cline_utils.dependency_system.dependency_processor generate-keys --root_paths  --output {doc_dir}/doc_tracker.md --tracker_type doc
```

*Replace with the actual path to your **documentation directory** (e.g., `docs/`). `{doc_dir}` is a placeholder for the documentation directory, as defined in the Core System Prompt.*

* **Important**: Do not manually create or modify tracker files; **always** use `dependency_processor.py` to ensure proper structure and data consistency. Use `generate-keys` for initial setup.

* Example Initial `.clinerules`:

        ```
        ---CLINE_RULES_START---
        [LAST_ACTION_STATE]
        last_action: "System Initialized"
        current_phase: "Set-up/Maintenance"
        next_action: "Initialize Core Files"
        next_phase: "Set-up/Maintenance"
        [LEARNING_JOURNAL]
        # Cline Project Learning Journal (.clinerules)
        # Add entries as insights emerge.
        ---CLINE_RULES_END---
        ```

3. **MUP**: Follow Core Prompt MUP after creating files.

---

## III. Populating `doc_tracker.md` (Documentation Dependency Tracker)

**Objective**: Fully populate `doc_tracker.md` in `{doc_dir}/` with verified dependencies (highest priority). **All tracker modifications MUST be done using the `dependency_processor.py` script.**

**Procedure**:

1. **File Existence Check**: Verify `doc_tracker.md` exists in `{doc_dir}/`. If not, create it with:

```
python -m cline_utils.dependency_system.dependency_processor generate-keys --root_paths {doc_dir} --output {doc_dir}/doc_tracker.md --tracker_type doc
```

* **Note**: Do not manually create; this command initializes the file with keys and a placeholder grid.

2. **Generate Embeddings**:

```
python -m cline_utils.dependency_system.dependency_processor generate-embeddings --root_paths {doc_dir} --output {doc_dir} --model all-MiniLM-L6-v2
```

3. **Suggest Dependencies**:

```
python -m cline_utils.dependency_system.dependency_processor suggest-dependencies --tracker {doc_dir}/doc_tracker.md --tracker_type doc
```

* **Note**: Validate suggestions before applying them. The command provides suggestions in JSON format; you must review these suggestions and choose the correct dependency character based on your understanding of the documentation links and relationships. You will typically run this command **once to get initial suggestions for the entire `doc_tracker.md`**.

4. **Validate and Set Dependencies**:

* Review JSON output from `suggest-dependencies`.
* Open the relevant files (row and column files from the suggestion).
* Confirm the dependency exists and determine the correct character (`<`, `>`, `x`, `d`, or `n`).
* Use `set_char` to set the character in the grid. You'll need the row key, the column index (from the X-axis header in the tracker file), and the chosen character.

```
python -m cline_utils.dependency_system.dependency_processor set_char --index  --new_char  --output {doc_dir}/doc_tracker.md --key 
```

5. **Iterate and Complete**: Repeat Steps 3-4 until no 'p' placeholders remain in `doc_tracker.md`. You will loop through files, suggesting dependencies for each, and then validating/setting those suggestions.

6. **MUP**: Apply Core MUP and Section VII additions after each `set_char` and completion.

---

## IV. Populating `dependency_tracker.md` (Module-Level Dependency Tracker)

**Objective**: Fully populate `dependency_tracker.md` in `{memory_dir}/` *after* `doc_tracker.md`. **All tracker modifications MUST be done using the `dependency_processor.py` script.**

**Procedure**:

1. **File Existence Check**: Verify that `dependency_tracker.md` exists in `{memory_dir}/`. If not, create it with:

```
python -m cline_utils.dependency_system.dependency_processor generate-keys --root_paths  --output {memory_dir}/dependency_tracker.md --tracker_type main
```

*Replace `` with the actual paths to your code root directories, i.e. "src tests".*

2. **Generate Embeddings**: **Generate embeddings *before* suggesting dependencies.**

```
python -m cline_utils.dependency_system.dependency_processor generate-embeddings --root_paths  --output {memory_dir} --model all-MiniLM-L6-v2
```

*Replace with the actual paths to your **code root directories**, i.e. "src tests". Replace `{memory_dir}` with the path to your project root directory (where `.clinerules` is located).*

* **Important:** The `--output` argument should be the *parent* directory of where you want the `embeddings` subdirectory to be created (e.g., the project root). Do *not* include `embeddings` in the path.

3. **Suggest Dependencies**:

```
python -m cline_utils.dependency_system.dependency_processor suggest-dependencies --tracker {memory_dir}/dependency_tracker.md --tracker_type main
```

* **Note**: This provides suggestions in JSON; validate and select the character based on your code's module-level dependencies. You will typically run this command **once to get initial suggestions for the entire `dependency_tracker.md`**.

4. **Validate and Set Dependencies**:

* Review the JSON output from `suggest-dependencies`.
* Open the relevant files (row and column files).
* Confirm the dependency and choose the correct character (`<`, `>`, `x`, `d`, or `n`).
* Use `set_char` to set the character in the grid:

```
python -m cline_utils.dependency_system.dependency_processor set_char --index  --new_char  --output {memory_dir}/dependency_tracker.md --key 
```

5. **Iterate and Complete**: Repeat Steps 3-4 until no 'p' placeholders remain.

6. **MUP**: Apply Core MUP and Section VIII additions after each `set_char` and completion.

---

## V. Dependency Tracker Management (Details)

### V.1 Dependency Characters

-   `<`: Row depends on column.
-   `>`: Column depends on row.
-   `x`: Mutual dependency.
-   `d`: Documentation dependency.
-   `o`: No dependency (diagonal only).
-   `n`: Verified no dependency.
-   `p`: Placeholder (unverified).
-   `s`: Semantic dependency

### V.2 Hierarchical Key System

- **Purpose**: Encodes hierarchy in trackers.
- **Structure**: Tier (number), Directory (uppercase), Subdirectory (lowercase), File (number).
- **Examples**: `1A` (top-level dir 'A'), `1A1` (first file in 'A'), `2Ba3` (third file in subdir 'a' of 'B').

### V.3 Grid Format and X-Axis Header

- **X-Axis Header**: "X " followed by column keys.
- **Dependency Rows**: Row key, " = ", compressed string (RLE, excluding 'o').

### V.4 Dependency Processor Commands

Located in `cline_utils/`. **All commands for the dependency system are executed through `dependency_processor.py`.** The LLM should always use these commands and should *never* attempt to directly call internal functions. Every command returns a dictionary in JSON format, with at least `status` and `message` keys to indicate success or failure.

**Placeholder Definitions:**

| Placeholder           | Description                                           | Example                                  |
|-----------------------|-------------------------------------------------------|------------------------------------------|
| `<path1>`, `<path2>`... | One or more file or directory paths                  | `src`, `docs`                             |
| `<tracker_path>`      | Path to a tracker file (`.md` file)                  | `cline_docs/dependency_tracker.md`        |
| `<file_path>`         | Path to a source code or documentation file            | `src/utils/helpers.py`                     |
| `<row_key>`           | Key identifying a row in the dependency grid           | `1A2`                                     |
| `<column_index>`      | Numerical index of a column in the dependency grid     | `5`                                       |
| `<character>`         | A dependency character (`<`, `>`, `x`, `d`, `n`, `p`, `s`) | `d`                                       |
| `<output_file>`       | Path to a file for command output                    | `exported_graph.json`                    |
| `<output_dir>`        | Path to a directory for command output               | `embeddings/`                              |
| `<project_root>`      | Path to the project root directory (`cline/`)          | `/path/to/your/cline/project/cline/`      |
| `<code_root_path>`...| Path to code root directories (from `.clinerules`)   | `src`                                     |
| `<doc_dir>`           | Path to documentation directory (e.g., `docs/`)        | `docs/`                                   |
| `{memory_dir}`        | Placeholder for memory directory (e.g., `cline_docs/`) | `cline_docs/`                              |

1. **`generate-keys`**: Initializes a tracker and adds all files/folders within the given root paths. Use this *once* per tracker to set up the initial structure.

```
python -m cline_utils.dependency_system.dependency_processor generate-keys --root_paths  --output  --tracker_type main|doc|mini
```

* `--root_paths`: One or more paths to scan for files/folders.
* `--output`: Path to the tracker file (e.g., `cline_docs/dependency_tracker.md`).
* `--tracker_type`: Optional. `main` (default), `doc`, or `mini`.

2. **`compress`**: Compresses a string using run-length encoding (RLE).

```
python -m cline_utils.dependency_system.dependency_processor compress 
```

* ``: String to compress.

3. **`decompress`**: Decompresses a string that was compressed using RLE.

```
python -m cline_utils.dependency_system.dependency_processor decompress 
```

* ``: String to decompress.

4. **`get_char`**: Gets the character at a specific index in a compressed string.

```
python -m cline_utils.dependency_system.dependency_processor get_char  
```

* ``: Compressed string.
* ``: Index.

5. **`set_char`**: Sets a character at a specific index in a compressed string and returns the compressed result.

```
python -m cline_utils.dependency_system.dependency_processor set_char --index  --new_char  --output  --key 
```

* `--index`: The index of the column (check the X-axis header in the tracker file).
* `--new_char`: The new character to set.
* `--output`: Path to the tracker file.
* `--key`: The key of the row.

6. **`remove-file`**: Removes a file from the tracker.

```
python -m cline_utils.dependency_system.dependency_processor remove-file  --output 
```

* ``: Path of the file to be removed.
* `--output`: Path to the tracker file.

7. **`suggest-dependencies`**: Suggests dependencies for a tracker based on code analysis or semantic similarity.

```
python -m cline_utils.dependency_system.dependency_processor suggest-dependencies --tracker  --tracker_type main|doc|mini
```

* `--tracker`: Path to the tracker file.
* `--tracker_type`: Type of the tracker file (`main`, `doc`, or `mini`).

15. **`generate_embeddings`**: Generates embeddings for files in the given root paths.
    ```bash
    python -m cline_utils.dependency_system.dependency_processor generate_embeddings --root_paths <path1> [<path2> ...] --output <output_dir> [--model <model_name>] [--embed_type doc|code|both]
    ```
    * `--root_paths`:  One or more root paths.
    * `--output`: The output directory.
    * `--model`: The name of the model.
    * `--embed_type`: The type of embedding to generate.

### V.5 Mini-Tracker Example

For `{module_dir}` = "utils":

1.  **Create and Populate**:

    ```bash
   python -m cline_utils.dependency_system.dependency_processor generate_keys --root_paths utils --output utils/utils_main_instructions.txt --tracker_type mini
    ```

2.  **Suggest Dependencies**:

    ```bash
    python -m cline_utils.dependency_system.dependency_processor suggest_missing_dependencies --tracker_path utils/utils_main_instructions.txt --file_path <file_path> --method combined
    ```

3.  **Validate and Set**:

    ```bash
    python -m cline_utils.dependency_system.dependency_processor set_dependency_character --tracker_path utils/utils_main_instructions.txt --key <row_key> --index <column_index> --new_char <character>
    ```

### V.6 Command Sequence Flowchart

```mermaid
flowchart TD
A[Generate Keys (One Time)] --> B[Generate Embeddings]
B --> C[Suggest Dependencies]
C --> D[Validate Suggestion]
D --> E[Set Character]
E --> F{No more 'p' placeholders?}
F -- No --> C
F -- Yes --> G[Complete]
```

---

## VI. Populating Mini-Trackers

**Objective**: Create and populate mini-trackers in `{module_dir}/{module_dir}_main_instructions.txt`.

**Procedure**:

1. **Identify Modules**: Use `dependency_tracker.md` directories.

2. **Instruction File Check**:

* If `{module_dir}/{module_dir}_main_instructions.txt` is missing:

* Create with basic structure (see Core Prompt, Section VII).

* Initialize mini-tracker:

```
python -m cline_utils.dependency_system.dependency_processor generate-keys --root_paths {module_dir} --output {module_dir}/{module_dir}_main_instructions.txt --tracker_type mini
```

* If it exists, proceed to Step 3.

3. **Generate Embeddings (if applicable)**: If you are tracking semantic dependencies within the module, generate embeddings:

```
python -m cline_utils.dependency_system.dependency_processor generate-embeddings --root_paths {module_dir} --output {module_dir} --model all-MiniLM-L6-v2
```

4. **Suggest and Validate**: See **Section V.5** for a full example of using `suggest-dependencies` and `set_char` to populate the mini-tracker grid. Use these commands in the same way as you did for the main and doc trackers, adapting the `--tracker` and keys accordingly.

5. **Iterate and Complete**: Repeat until populated.

6. **MUP**: Apply Core MUP and Section VII additions.

---

## VII. Set-up/Maintenance Plugin - MUP Additions

After Core MUP steps:

1. **Update `dependency_tracker.md`**: Save changes from commands.

2. **Update `doc_tracker.md`**: Save changes.

3. **Update Mini-Trackers**: Save changes.

4. **Update `.clinerules` [LAST_ACTION_STATE]**:

* Example after `doc_tracker.md`:

        ```
        ---CLINE_RULES_START---
        [LAST_ACTION_STATE]
        last_action: "Populated doc_tracker.md"
        current_phase: "Set-up/Maintenance"
        next_action: "Populate dependency_tracker.md"
        next_phase: "Set-up/Maintenance"
        [LEARNING_JOURNAL]
        # ...
        ---CLINE_RULES_END---
        ```

---
