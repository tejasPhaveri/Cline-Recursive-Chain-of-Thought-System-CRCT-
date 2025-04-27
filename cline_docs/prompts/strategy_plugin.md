# **Cline Recursive Chain-of-Thought System (CRCT) - Strategy Plugin v7.6**

**This Plugin provides detailed instructions and procedures for the Strategy phase of the CRCT system. It guides the critical process of translating the high-level system design into a sequenced and actionable implementation plan based on verified project dependencies. Use this in conjunction with the Core System Prompt.**

---

**Entering and Exiting Strategy Phase**

**Entering Strategy Phase:**
1.  **`.clinerules` Check (Mandatory First Step)**: Read `.clinerules` file content.
2.  **Determine Current State**:
    *   If `[LAST_ACTION_STATE]` section indicates `current_phase: "Strategy"`, proceed with the instructions below, starting from the action indicated by `next_action`.
    *   If `[LAST_ACTION_STATE]` section indicates `next_phase: "Strategy"`, this signifies a transition from a previous phase (likely Set-up/Maintenance). Proceed with the instructions below, starting from **Section II, Step 1**.
3.  **User Trigger**: If starting a new session and `.clinerules` indicates the system *was* in Strategy or *should transition* to Strategy, proceed with these instructions.

**Exiting Strategy Phase:**
1.  **Completion Criteria (Mandatory Check)**: Verify ALL the following are met:
    *   A clear implementation sequence based on dependency analysis has been defined (documented in Implementation Plans or `activeContext.md`).
    *   All high-priority work planned for this strategy cycle has been decomposed into atomic Task Instructions.
    *   Necessary supporting HDTA documents (Domain Modules, Implementation Plans) have been created or updated.
    *   Tasks have been prioritized for the Execution phase (documented in `activeContext.md`).
    *   All HDTA documents have been correctly linked (Tasks from Plans, Plans from Modules, Modules from Manifest).
2.  **`.clinerules` Update (Mandatory MUP Step)**: If completion criteria are met, update `.clinerules` **exactly** as follows:
    ```
    [LAST_ACTION_STATE]
    last_action: "Defined Implementation Sequence and Prioritized Tasks"
    current_phase: "Strategy"
    next_action: "Phase Complete - User Action Required"
    next_phase: "Execution"
    ```
3.  **Pause for User Action**: After successfully updating `.clinerules`, state that the Strategy phase is complete and you are awaiting user action (e.g., a new session start) to begin the Execution phase. Do not proceed further in this session.

## I. Phase Objective & Guiding Principles

**Objective**: To define a clear, dependency-aware **implementation roadmap** for the current development cycle. This involves strategically decomposing goals into actionable tasks, determining the correct build order based on verified dependencies, creating necessary planning documents (HDTA), and prioritizing work for the Execution phase.

**Guiding Principles**:
1.  **Dependency-Driven Sequencing**: The verified relationships ('<', '>', 'x', 'd') in the trackers (`doc_tracker.md`, mini-trackers, `module_relationship_tracker.md`) are the **primary guide** for determining task order. Use `show-dependencies` extensively to understand constraints.
2.  **Plan Top-Down, Build Bottom-Up**: Define the strategy starting from high-level goals (`system_manifest.md`, `activeContext.md`) and progressively decompose them through Domain Modules, Implementation Plans, and finally into specific Tasks. However, the *execution order* is determined by starting with foundational tasks (those with no '<' dependencies) and building upwards.
3.  **Strategic HDTA Creation**: HDTA documents (Modules, Plans, Tasks) are not just documentation; they are the **structured output of the strategic planning process**, capturing objectives, steps, context, and dependencies for each work unit. Create them *as needed* to define the plan.
4.  **Minimal Context, Maximum Guidance**: Focus on creating clear, concise instructions and plans that provide the Execution phase with the necessary guidance and context links without unnecessary detail.

---

## II. Strategic Planning Workflow: Defining the Implementation Roadmap

**Directive**: Develop the implementation roadmap by systematically decomposing goals, rigorously analyzing dependencies and their underlying meaning, sequencing granular tasks, creating required HDTA documents precisely, and prioritizing work for focused execution.

**Procedure**:

1.  **Review Current State & Goals**:
    *   **Action**: Read and analyze `activeContext.md` for current priorities, decisions, and cycle goals.
    *   **Action**: Read and analyze `system_manifest.md` for system architecture and component overview.

2.  **Identify Target Area(s)**:
    *   **Action**: Based on Step 1, explicitly state the primary module(s) or feature(s) selected as the focus for this planning cycle.

3.  **Analyze Dependencies & Understand Interactions**:
    *   **CRITICAL STEP**: For the target area(s), use the dependency system not just to *identify* constraints but to *understand* the nature of the interactions *before* detailed planning. This is mandatory for correct sequencing.
    *   **Action**: Execute `show-dependencies --key <relevant_key>` for key files or modules involved (e.g., the main module key like `1Ba`, or a specific file key like `1Ba2` if planning modifications).
    *   **Interpret Dependencies**:
        *   `Depends On ('<')`: Files/modules listed here are **prerequisites**. Work involving `<relevant_key>` cannot start until work on these prerequisites is complete.
            * When show-dependencies returns '<' relationship:  
               1. Read source/target files via read_file  
               2. Perform line-level analysis:  
                  - Function/method calls  
                  - Class inheritance  
                  - Documentation references  
               3. Confirm relationship type matches actual usage
        *   `Depended On By ('>')`: Files/modules listed here **rely on** `<relevant_key>`. Changes to `<relevant_key>` may impact these downstream components.
        *   `Documentation ('d')`: Indicates essential documentation links. Ensure linked docs are understood or planned for creation/update alongside the related code/module.
        *   `Mutual ('x')`: Suggests tightly coupled components that might need coordinated development or careful sequencing.
    *   Review relevant sections of `doc_tracker.md`, mini-trackers (`*_module.md`), and `module_relationship_tracker.md` (using `show-keys` and `show-dependencies`) to confirm the relationships identified.
    *   **MANDATORY: Deepen Understanding Beyond Characters**: The dependency characters provide a map, but **true strategic planning requires understanding the terrain**. You **MUST** use `read_file` to examine the *content* of the files associated with the most critical dependencies (especially '<', '>', 'x', 'd') identified by `show-dependencies`. Ask:
        *   *Why* does A depend on B? Is it a function call, data structure usage, conceptual prerequisite, setup requirement?
        *   What *specific* parts of file B are relevant to file A?
        *   What is the *implication* of this dependency for implementation order and potential refactoring?
    *   This deeper understanding is essential for accurate decomposition and sequencing in the following steps.

4.  **Decompose & Define HDTA Structure (Top-Down Planning, Atomic Tasks)**:
   *   **Directive**: Based on goals and the *understanding* from Step 3, determine the necessary HDTA documents. Decompose work into the smallest logical, actionable units suitable for execution with limited context.
   *   **Recursive Decomposition for Execution:** Break down work identified in Implementation Plans into the smallest logical, actionable units. The goal is to create **atomic Task Instructions (`*.md`)** that can be executed independently by an LLM with a **limited context window**.
      *   Each Task Instruction should represent a single, focused change (e.g., implement one function, modify a specific class method, update a section of documentation).
      *   Crucially, each Task Instruction file must explicitly list *only* the **minimal necessary context** (links to specific function definitions, relevant documentation keys/sections, data structures) required to complete *that specific task*, derived from your analysis in Step 3. Avoid linking unnecessary files.
   *   **HDTA Document Creation/Update**:
      *   **Action**: For each required HDTA document (Domain Module, Implementation Plan, Task Instruction):
         *   **A. Existence Check (Mandatory)**: Check if the target file path already exists.
            *   **B. Decision & Rationale**:
               *   If exists and current content is sufficient/accurate for the plan: State "File `{file_path}` exists and is sufficient. No update needed." Proceed to next document/step.
               *   If exists but outdated/incomplete: State "File `{file_path}` exists but needs updates. Proceeding to update."
               *   If not exists: State "File `{file_path}` does not exist. Proceeding to create."
            *   **C. Create/Update**: If creation or update is needed, use `write_to_file`. Load the appropriate template from `cline_docs/templates/`. Fill in **all required sections** of the template with precise details based on your analysis.
        *   **Specific Document Content Directives**:
            *   **Domain Module (`*_module.md`)**: Required if planning involves a new major functional area or significant changes to an existing one. Use the template (`module_template.md`) to define its purpose, interfaces, and scope *within the context of the overall system and its dependencies*. If creating a new module, remember to manually add it to `system_manifest.md`.
            Include relevant **Implementation Details** (key files, algorithms, models planned *for this module*). List associated Implementation Plans.
            *   **Implementation Plan (`implementation_plan_*.md`)**: Required for planning features or groups of related changes affecting multiple files. Use the template (`implementation_plan_template.md`) to outline the high-level approach, affected components (linking to their keys/docs), and major steps. Link this plan from the relevant Domain Module(s).
            Detail **Design Decisions**, **Algorithms**, and **Data Flow** relevant *to this specific plan*. List the sequence of atomic **Task Instructions** required to fulfill this plan.
            *   **Task Instruction (`*.md`)**: Required for specific, actionable implementation steps within an Implementation Plan. Use the template (`task_template.md`) to detail the objective, **precise step-by-step instructions**, *minimal necessary context links*, **explicit `Dependencies` (Requires/Blocks task links)**, and expected output for *one atomic task*. Reference its parent Implementation Plan.
   *   **Linking (Mandatory)**:
       *   Add new Domain Modules to `system_manifest.md` registry.
       *   Link Implementation Plans from their parent Domain Module.
       *   Link Task Instructions from their parent Implementation Plan.
       *   Fill the `Dependencies` (Requires/Blocks) section in Task Instructions.
   *   **Add Missing Dependency Links**: While defining HDTA documents, if you identify crucial dependency links (especially code-to-doc) that were missed during Set-up/Maintenance and are necessary for context, use `add-dependency` to add them to the appropriate tracker (usually the mini-tracker for the code file). State your reasoning clearly.

5.  **Determine Build Sequence (Bottom-Up Execution Order)**:
   *   **Directive**: Sequence the **atomic Task Instructions** defined in Step 4 based *primarily* on the **understood** dependencies ('<', '>', 'x', 'd') analyzed in Step 3.
      *   Identify foundational tasks/components: Those with no outgoing '<' dependencies within the current scope of work. These should generally be implemented first.
      *   Sequence subsequent tasks: Order subsequent tasks ensuring prerequisites are met according to your understanding of the interactions (not just the characters). For 'x' dependencies, plan for potentially iterative or closely coordinated implementation steps across the linked tasks.
   *   Document the final sequence and the dependency-based rationale within the relevant Implementation Plan(s) or the module's `*_module.md` file.

6.  **Prioritize Tasks within Sequence**:
   *   Within the determined build sequence, prioritize tasks based on:
      *   Urgency/importance defined in `activeContext.md`.
      *   Potential to unblock other tasks.
      *   Logical grouping of related work.
   *   Record the final prioritization order and explicit reasoning within the relevant Implementation Plan(s) or the module's `*_module.md` file.

7.  **Present Plan**: Summarize the planned work, the determined sequence, the created/updated HDTA documents, and the task prioritization for user review and confirmation.

Task Planning Flowchart
```mermaid
flowchart TD
A[Start] --> B[Decompose Task Recursively]
B --> C[Define Objectives]
C --> D[Outline Steps]
D --> E[Assess Dependencies]
E --> F[Consider Alternatives]
F --> G[Define Expected Output]
G --> H[Prioritize Tasks]
H --> I[Update activeContext.md]
I --> J[Present Plan]
J --> K[End]
---

## III. Strategy Plugin - Mandatory Update Protocol (MUP) Additions

After Core MUP steps:
1.  **Save HDTA Documents**: Ensure all new or modified Domain Modules, Implementation Plans, and Task Instructions are saved.
2.  **Update `system_manifest.md`**: Add links to any *new* Domain Modules created.
3.  **Update Linking HDTA Docs**: Ensure Implementation Plans link to their Tasks, and Domain Modules link to their Implementation Plans.
4.  **Update `activeContext.md` with Strategy Outcomes**:
    *   Summarize the overall strategy and implementation sequence determined.
    *   List key HDTA documents created/updated (especially new Plans and prioritized Tasks).
    *   Document task priorities and the dependency-based reasoning for the sequence (from Section II, Steps 5 & 6).
5.  **Update `.clinerules` [LAST_ACTION_STATE]:**
    ```
    [LAST_ACTION_STATE]
    last_action: "Defined Implementation Sequence and Prioritized Tasks"
    current_phase: "Strategy"
    next_action: "Phase Complete - User Action Required"
    next_phase: "Execution"
    ```

---

## IV. Quick Reference

-   **Goal**: Create a dependency-aware implementation roadmap.
-   **Key Actions**:
    *   Analyze dependencies (`show-dependencies`).
    *   Decompose goals (top-down).
    *   Define HDTA documents strategically (Modules, Plans, Tasks).
    *   Determine build sequence based on dependencies (bottom-up execution).
    *   Prioritize tasks within the sequence.
    *   *Manually* link HDTA documents and add critical missing dependencies via `add-dependency`.
-   **Key Inputs**: `activeContext.md`, `system_manifest.md`, Verified Trackers.
-   **Key Outputs**: Updated `activeContext.md`, new/updated HDTA documents, updated `.clinerules`.
-   **MUP Additions**: Save HDTA, update `system_manifest.md` (if needed), update `activeContext.md`, update `.clinerules`.
