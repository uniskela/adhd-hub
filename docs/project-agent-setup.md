# Keep each project connected

Use the CLI once in a project folder to add a small, reversible ADHD Hub section to that folder's `AGENTS.md`:

```bash
adhd-hub setup /path/to/my-project
```

The managed section tells a coding agent to resolve the project, check the existing digest and overlap before work, save short progress when pausing, and close only its own thread when finished. It also reminds the agent not to send secrets or full transcripts.

The command is safe to repeat. It updates only the section between these markers and preserves the rest of `AGENTS.md`:

```text
<!-- adhd-hub:project-agent:start -->
<!-- adhd-hub:project-agent:end -->
```

## Install the skills too

Skill installation is opt-in because it changes the global skills directory and may use the network:

```bash
# From the public repository
adhd-hub setup /path/to/my-project --install-skills

# From a local checkout while developing
adhd-hub setup /path/to/my-project \
  --install-skills --skills-source /path/to/adhd-hub/skills
```

This runs `npx skills add <source> -g` without a shell, so paths and arguments are not interpolated as commands. Review the source and keep the MCP bearer token in an environment variable; never add it to `AGENTS.md`.

## Remove the managed section

```bash
adhd-hub setup /path/to/my-project --uninstall
```

Only the ADHD Hub block is removed. The command refuses to edit a symlink or an incomplete managed block.
