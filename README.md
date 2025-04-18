# Cline Recursive Chain-of-Thought System (CRCT) - v7.5

Welcome to the **Cline Recursive Chain-of-Thought System (CRCT)**, a framework designed to manage context, dependencies, and tasks in large-scale Cline projects within VS Code. Built for the Cline extension, CRCT leverages a recursive, file-based approach with a modular dependency tracking system to maintain project state and efficiency as complexity increases.

Version **v7.5** represents a significant restructuring of the CRCT system, bringing it into alignment with its original design goals.  With the core architecture now established, future v7.x releases will focus on performance optimizations, enhancements, and refining the existing codebase.

This version includes a more automated design, consolidating operations and enhancing efficiency.
It also incorporates:
- base templates for all core files
- modular dependency processing system
- **Contextual Keys (KeyInfo)**: A fundamental shift to using contextual keys for more precise and hierarchical dependency tracking.
- **Hierarchical Dependency Aggregation**:  Enables rolled-up dependency views in the main tracker, offering a better understanding of project-level dependencies.
- **Enhanced `show-dependencies` command**: Provides a powerful way to inspect dependencies, aggregating information from all trackers for a given key, simplifying dependency analysis.
- **Configurable Embedding Device**:  Allows users to optimize performance by selecting the embedding device (`cpu`, `cuda`, `mps`) via `.clinerules.config.json`.
- **File Exclusion Patterns**:  Users can now customize project analysis by defining file exclusion patterns in `.clinerules.config.json`.
- **Improved Caching and Batch Processing**: Enhanced system performance and efficiency through improved caching and batch processing mechanisms.

**<<<IMPORTANT_NOTICE>>>**

Caching has passed initial tests and has been re-enabled across the system. If you notice odd behavior or inaccuracies, please report them in the github issues section.
- If issues arise **comment** (`#`) out the `@cached` decorators and the lines leading up to the def  (`# @cached(...)`)

Cache + batch processing enable *significant* time savings.
- Test project **without** cache and batch processing took ~`11` minutes.
- Test project **with** cache and batch processing took ~`30` seconds.

**<<<END_IMPORTANT_NOTICE>>>**

---

## Key Features

- **Recursive Decomposition**: Breaks tasks into manageable subtasks, organized via directories and files for isolated context management.
- **Minimal Context Loading**: Loads only essential data, expanding via dependency trackers as needed.
- **Persistent State**: Uses the VS Code file system to store context, instructions, outputs, and dependencies—kept up-to-date via a **Mandatory Update Protocol (MUP)**.
- **Modular Dependency System**: Fully modularized dependency tracking system.
- **Contextual Keys**: Introduces `KeyInfo` for context-rich keys, enabling more accurate and hierarchical dependency tracking.
- **Hierarchical Dependency Aggregation**: Implements hierarchical rollup and foreign dependency aggregation for the main tracker, providing a more comprehensive view of project dependencies.
- **New `show-dependencies`command**: The LLM no longer has to manually read and decipher tracker files. This arg will automatically read all trackers for the provided key and return both inbound and outbound dependencies with a full path to each related file. (The LLM still needs to manually replace any placeholder characters 'p', but can now do so with the `add-dependency` command, greatly simplifying the process.)
- **Configurable Embedding Device**: Allows users to configure the embedding device (`cpu`, `cuda`, `mps`) via `.clinerules.config.json` for optimized performance on different hardware. (Note: *the system does not yet install the requirements for cuda or mps automatically, please install the requirements manually or with the help of the LLM.*)
- **File Exclusion Patterns**: Users can now define file exclusion patterns in `.clinerules.config.json` to customize project analysis.
- **New Cache System**: Implemented a new caching mechanism for improved performance, including improved invalidation logic.
- **New Batch Processing System**: Introduced a batch processing system for handling large tasks efficiently, with enhanced flexibility in passing arguments to processor functions.
- **Modular Dependency Tracking**:
  - Mini-trackers (file/function-level within modules)
  - Uses hierarchical keys and RLE compression for efficiency.
- **Automated Operations**: System operations are now largely automated and condensed into single commands, streamlining workflows and reducing manual command execution.
- **Phase-Based Workflow**: Operates in distinct phases—**Set-up/Maintenance**, **Strategy**, **Execution**—controlled by `.clinerules`.
- **Chain-of-Thought Reasoning**: Ensures transparency with step-by-step reasoning and reflection.

---

## Quickstart

1. **Clone the Repo**:
   ```bash
   git clone https://github.com/RPG-fan/Cline-Recursive-Chain-of-Thought-System-CRCT-.git
   cd Cline-Recursive-Chain-of-Thought-System-CRCT-
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Set Up Cline Extension**:
   - Open the project in VS Code with the Cline extension installed.
   - Copy `cline_docs/prompts/core_prompt(put this in Custom Instructions).md` into the Cline system prompt field.

4. **Start the System**:
   - Type `Start.` in the Cline input to initialize the system.
   - The LLM will bootstrap from `.clinerules`, creating missing files and guiding you through setup if needed.

*Note*: The Cline extension’s LLM automates most commands and updates to `cline_docs/`. Minimal user intervention is required (in theory!).

---

## Project Structure

```
Cline-Recursive-Chain-of-Thought-System-CRCT-/
│   .clinerules
│   .gitignore
│   INSTRUCTIONS.md
│   LICENSE
│   README.md
│   requirements.txt
│
├───cline_docs/                   # Operational memory
│   │  activeContext.md           # Current state and priorities
│   │  changelog.md               # Logs significant changes
│   │  userProfile.md             # User profile and preferences
│   ├──backups/                   # Backups of tracker files
│   ├──prompts/                   # System prompts and plugins
│   │    core_prompt.md           # Core system instructions
│   │    execution_plugin.md
│   │    setup_maintenance_plugin.md
│   │    strategy_plugin.md
│   ├──templates/                 # Templates for HDTA documents
│   │    implementation_plan_template.md
│   │    module_template.md
│   │    system_manifest_template.md
│   │    task_template.md
│
├───cline_utils/                  # Utility scripts
│   └─dependency_system/
│     │ dependency_processor.py   # Dependency management script
│     ├──analysis/                # Analysis modules
│     ├──core/                    # Core modules
│     ├──io/                      # IO modules
│     └──utils/                   # Utility modules
│
├───docs/                         # Project documentation
└───src/                          # Source code root

```

---

## Current Status & Future Plans

- **v7.5**:  This release marks a significant restructuring of the CRCT system, bringing it into alignment with its original design goals. **Key architectural changes include the introduction of Contextual Keys (`KeyInfo`) and Hierarchical Dependency Aggregation, enhancing the precision and scalability of dependency tracking.** Key features also include the new `show-dependencies` command for simplified dependency inspection, configurable embedding device, and file exclusion patterns.
- **Efficiency**: Achieves a ~1.9 efficiency ratio (90% fewer characters) for dependency tracking compared to full names, with efficiency improving at larger scales.
- **Savings for Smaller Projects & Dependency Storage**: Version 7.5 enhances dependency storage and extends efficiency benefits to smaller projects, increasing CRCT versatility.
- **Automated Design**: System operations are largely automated, condensing most procedures into single commands such as `analyze-project`, which streamlines workflows.
- **Future Focus**: With the core architecture of v7.5 established, future development will concentrate on performance optimizations, enhancements, and the refinement of existing functionalities within the v7.x series. **Specifically, future v7.x releases will focus on performance optimizations, enhancements to the new `show-dependencies` command, and refining the existing codebase.**

Feedback is welcome! Please report bugs or suggestions via GitHub Issues.

---

## Getting Started (Optional - Existing Projects)

To test on an existing project:
1. Copy your project into `src/`.
2. Use these prompts to kickstart the LLM:
   - `Perform initial setup and populate dependency trackers.`
   - `Review the current state and suggest next steps.`

The system will analyze your codebase, initialize trackers, and guide you forward.

---

## Thanks!

A big Thanks to https://github.com/biaomingzhong for providing detailed instructions that were integrated into the core prompt and plugins! (PR #25)

This is a labor of love to make Cline projects more manageable. I’d love to hear your thoughts—try it out and let me know what works (or doesn’t)!
