I've been working on a way to manage context and dependencies in larger Cline projects, especially as the project grows and the context window starts to fill up. Inspired by the Cline memory bank, I've developed a system prompt called the **Cline Recursive Chain-of-Thought System (CRCT)** that I'd like to share.

The core problem I wanted to solve was keeping track of all the interdependencies between files, modules, and documentation, and ensuring the LLM always has the *right* context loaded at the *right* time. This system uses a recursive, file-based approach with a very strict dependency tracking system and a mandatory update protocol to address that.

---
**QUICKSTART**
Just copy the content of the CRCT prompt file and paste it into the area for cline's system prompt. The system should be able to bootstrap off very little information by asking you a few guiding questions, but I'd suggest at least getting a rough plan together to start with.
---

Here's a quick rundown of the key features:

* **Recursive Decomposition:** Tasks are broken down into smaller, manageable subtasks, organized using directories and files. This helps to isolate context and keep things organized.
* **Minimal Context Loading:** Only essential information is loaded initially. The system relies heavily on the dependency trackers to load additional context *only* when needed.
* **Persistent State:** The Cline VS Code file system is used for persistent storage of everything: context, instructions, outputs, and (most importantly) dependencies.
* **Explicit & Automated Dependency Tracking:** This is the heart of the system. It uses a main `dependency_tracker.md` file (for module-level and documentation dependencies) and "mini-trackers" within instruction files (for file-level and function-level dependencies). A shortcode system keeps things efficient.
* **Mandatory Update Protocol:** This is a strict rule: *any* time *anything* changes in the project (a file is created, a dependency is added, a plan is revised), the LLM *must* immediately update the relevant trackers and the `activeContext.md` file. This keeps the persistent state consistent.
* **Multi-tiered Instruction Files:** The system uses "main task instruction files" (for directories) and "file-specific instruction files" to provide clear, granular instructions.

It's still a work in progress, and I'm actively refining it. I'd be incredibly grateful for any feedback, suggestions, or bug reports if you decide to try it out!

**Getting Started (Optional - for testing on existing projects):**

If you want to try this on a copy of an existing project, here are a couple of helpful starting statements to get the LLM going:

1. `Perform a project-wide dependency analysis and update the dependency_tracker.md file.`
2. `Before we move on, are you sure the edits you made are all appropriate?`

These statements help kickstart the dependency tracking and encourage the LLM to double-check its work, which is crucial for this system.

Thanks for taking a look! Let me know what you think.
