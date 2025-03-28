# Cline Recursive Chain-of-Thought System (CRCT) - v7.2

Welcome to the **Cline Recursive Chain-of-Thought System (CRCT)**, a framework designed to manage context, dependencies, and tasks in large-scale Cline projects within VS Code. Built for the Cline extension, CRCT leverages a recursive, file-based approach with a modular dependency tracking system to keep your project's state persistent and efficient, even as complexity grows.

This is **v7.2**, the initial release of the fully modularized dependency system, marking a significant transition from the basic v7.0. This version introduces a more automated design, consolidating operations and enhancing efficiency, and includes base templates for all core files and the `dependency_processor.py` script.

(This README and INSTRUCTIONS.md will be updated to reflect more granular changes over the next few days)

---

## Key Features

- **Recursive Decomposition**: Breaks tasks into manageable subtasks, organized via directories and files for isolated context management.
- **Minimal Context Loading**: Loads only essential data, expanding via dependency trackers as needed.
- **Persistent State**: Uses the VS Code file system to store context, instructions, outputs, and dependencies—kept up-to-date via a **Mandatory Update Protocol (MUP)**.
- **Modular Dependency System**: Fully modularized dependency tracking system.
- **New Cache System**: Implemented a new caching mechanism for improved performance.
- **New Batch Processing System**: Introduced a batch processing system for handling large tasks efficiently.
- **Modular Dependency Tracking**:
  - Mini-trackers (file/function-level within modules)
  - Uses hierarchical keys and RLE compression for efficiency.
- **Automated Operations**: System operations are now largely automated and condensed into single commands, streamlining workflows and reducing manual command execution.
- **New `show-dependencies`command**: The LLM no longer has to manually read and decipher tracker files. This arg will automatically read all trackers for the provided key and return both inbound and outbound dependencies with a full path to each related file. (The LLM still needs to manually replace any placeholder characters 'p', but can now do so with the `add-dependency` command, greatly simplifying the process.)
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

- **v7.2**: Initial full release of the modular dependency system, new cache system, and batch processing system. Includes templates for all `cline_docs/` files. This release marks a significant step towards a more automated and efficient system.
- **Efficiency**: Achieves a ~1.9 efficiency ratio (90% fewer characters) for dependency tracking vs. full names—improving with scale.
- **Savings for Smaller Projects & Dependency Storage**: This version refines dependency storage and extends efficiency savings to smaller projects, making CRCT more versatile.
- **Automated Design**: System operations are now largely automated, condensing most procedures into single commands like `analyze-project`, streamlining workflows.
- **Ongoing Development**: Continued development will focus on further refinements and optimizations of the modular system.

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

This is a labor of love to make Cline projects more manageable. I’d love to hear your thoughts—try it out and let me know what works (or doesn’t)!
