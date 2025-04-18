# **Cline Recursive Chain-of-Thought System (CRCT) - Strategy Plugin**

**This Plugin provides detailed instructions and procedures for the Strategy phase of the CRCT system. It should be used in conjunction with the Core System Prompt.**

---

## I. Entering and Exiting Strategy Phase

**Entering Strategy Phase:**
1. **`.clinerules` Check**: Always read `.clinerules` first. If `[LAST_ACTION_STATE]` shows `current_phase: "Strategy"`, proceed with these instructions.
2. **Transition from Set-up/Maintenance**: Enter after Set-up/Maintenance; `.clinerules` `next_phase` will be "Strategy".
3. **User Trigger**: Start a new session after Set-up/Maintenance or to resume strategy.

**Exiting Strategy Phase:**
1. **Completion Criteria:**
   - Domain Module and Task Instruction documents for prioritized tasks are created, with objectives, context, and steps defined.
   - Tasks are prioritized and ready for execution.
   - Strategy objectives for the cycle are met.
2. **`.clinerules` Update (MUP):**
   ```
   last_action: "Completed Strategy Phase - Tasks Planned"
   current_phase: "Strategy"
   next_action: "Phase Complete - User Action Required"
   next_phase: "Execution"
   ```
3. **User Action**: After updating `.clinerules`, pause for user to trigger Execution phase via a new session. See Core System Prompt, Section III for a phase transition checklist.

---

## II. Loading Context for Strategy

**Action**: Load context to guide strategy.
**Procedure:**
- Load core files: `.clinerules`, `system_manifest.md`, `activeContext.md`.
- Review `system_manifest.md` for system overview and component relationships.
- Review `activeContext.md` for current state, decisions, and priorities.
- Check `module_relationship_tracker.md` and `doc_tracker.md` for module and documentation dependencies.

---

## III. Creating New HDTA Documents

**Action**: Create *Domain Module* (`{module_name}_module.md`), *Implementation Plans* (`implementation_plan_{filename}.md`) and *Task Instruction* (`{task_name}.md`) documents as needed, ensuring no unnecessary overwrites.

**Procedure:**

1.  **Determine Document Tier:** Based on the task, decide which documents to create.
    *   **Domain Module:**  For defining new major functional areas or significantly modifying existing ones.
    *   **Implementation Plan** High level file plans.
    *   **Task Instruction:**  For specific, actionable tasks within an Implementation plan.

2.  **Choose Document Name and Location:**
    *   **Domain Module:** `{module_name}_module.md` in the appropriate directory (you may need to create a directory for the module).
    *   **Implementation Plan:** `implementation_plan_{filename}.md` in the appropriate directory.
    *   **Task Instruction:** `{task_name}.md` in the appropriate directory.

3.  **Pre-Action Verification:**
    *   Check if the intended file already exists.
    *   Generate Chain-of-Thought:
        *   If exists: "File `{file_name}.md` exists. Reviewing contents to confirm sufficiency."
        *   If not: "File `{file_name}.md` does not exist. Proceeding to create."
    *   Decide:
        *   Exists and sufficient: Skip creation.
        *   Exists but outdated: Update file.
        *   Does not exist: Create new file.

4.  **Populate Document Using Template:**
    *   Use the appropriate template from `cline_docs/templates/`.
    *   Fill in all sections of the template.
    *   Define clear objectives, key steps, dependencies, and expected        outputs for the document, ensuring alignment with project goals.

5.  **Manual Dependency Linking (CRITICAL):**
    *   **Domain Module:**  Add a link to the new Module in the `system_manifest.md` "Component Registry" section.
    *   **Implementation Plan** Add a link to the appropriate files.
    *   **Task Instruction:** Add a link to the appropriate files' "Tasks" section (or similar).
    * **YOU MUST MANUALLY MAINTAIN THESE LINKS.**

6.  **MUP**: Follow Core MUP and Section V additions after creating/updating files.

---

## IV. Task Decomposition and Prioritization

**Action**: Break down complex tasks into manageable subtasks, prioritize them, and plan their implementation.

**Procedure**:
1. **Recursive Decomposition**:
   - Break large tasks into smaller, well-defined subtasks. Continue decomposing until subtasks are actionable and specific.
   - Organize subtasks hierarchically (e.g., Feature → Sub-feature → Task).
2. **Define Objectives**:
   - For each task/subtask, state its objective clearly, aligning with `system_manifest.md` goals.
3. **Outline Steps**:
   - List key steps required to complete each task/subtask, ensuring clarity and feasibility.
4. **Assess Dependencies**:
   - Use `module_relationship_tracker.md`, `doc_tracker.md`, and mini-trackers to identify prerequisite tasks or modules.
   - Note dependencies that must be resolved first.
5. **Consider Alternatives**:
   - Explore different approaches or design patterns, discussing trade-offs where relevant.
6. **Define Expected Output**:
   - Describe the successful outcome of each task (e.g., files created, functionality implemented).
7. **Prioritize Tasks**:
   - Review existing tasks in module or task directories.
   - Prioritize based on dependencies, project goals, and recent priorities in `activeContext.md`.
   - Record prioritization reasoning in `activeContext.md`.
8. **Present Plan**:
   - Share the task breakdown and prioritization with the user for feedback before proceeding.

### IV.1 Task Planning Flowchart
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

## V. Strategy Plugin - Mandatory Update Protocol (MUP) Additions

After Core MUP steps:
1. **Update HDTA Documents**: Save new or modified documents.
2. **Update `system_manifest.md`**: Ensure links to new Components are added.
3. **Update Relevant Domain Modules**: Ensure links to new Instructions are added.
4. **Update `activeContext.md` with Strategy Outcomes:**
   - Summarize planned tasks.
   - List new instruction file locations and names.
   - Document priorities and reasoning (from Section IV).
5. **Update `.clinerules` [LAST_ACTION_STATE]:**
   ```
   [LAST_ACTION_STATE]
   last_action: "Completed Strategy Phase - Tasks Planned"
   current_phase: "Strategy"
   next_action: "Phase Complete - User Action Required"
   next_phase: "Execution"
   ```

---

## VI. Quick Reference
- **Actions:**
  - Create HDTA documents: Define modules, implementation plans, and tasks/subtasks.
  - Prioritize tasks: Assess dependencies and goals.
  - *Manually* link documents: Maintain the HDTA hierarchy.
- **Files:**
  - `system_manifest.md`: Guides objectives.
  - `activeContext.md`: Tracks state and priorities.
  - `module_relationship_tracker.md`: Lists dependencies.
  - Domain Module documents: Describe functional areas.
  - Task Instruction documents: Outline specific tasks.
- **MUP Additions:** Update HDTA documents, `system_manifest.md`, `activeContext.md`, and `.clinerules`.
