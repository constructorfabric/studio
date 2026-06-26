# Kit Thin Domain Routing

```pdsl
UNIT KitThinDomainClassify
PURPOSE: Classify the scoped kit work so the kit thin workflows can delegate to the correct specialist workflow.
STATE:
  SET KIT_WORK_DOMAIN: prompting | documenting | coding | manifest | mixed | unset (default unset, scope workflow_run)
DO:
  SET KIT_WORK_DOMAIN = manifest WHEN explicit target paths, author targets, review targets, or the user's request name `.cf-studio-kit.toml`, `manifest.toml`, `conf.toml`, or other kit registration/config files directly
  SET KIT_WORK_DOMAIN = prompting WHEN KIT_WORK_DOMAIN == unset AND explicit target paths, author targets, or review targets point to workflow, skill, agent-instruction, or other prompt-contract files such as `workflows/`, `skills/`, `agents/`, `SKILL.md`, or `AGENTS.md`
  SET KIT_WORK_DOMAIN = documenting WHEN KIT_WORK_DOMAIN == unset AND explicit target paths, author targets, or review targets point to README, guide, checklist, example, template, or other human-facing documentation files
  SET KIT_WORK_DOMAIN = coding WHEN KIT_WORK_DOMAIN == unset AND explicit target paths, author targets, or review targets point to scripts, tests, validators, generators, utilities, or executable source files
  SET KIT_WORK_DOMAIN = prompting WHEN ORIGINAL_INTENT primarily asks to create, edit, review, validate, or fix prompt files, skills, workflows, agents, rules, system instructions, or other prompt-contract assets inside a kit
  SET KIT_WORK_DOMAIN = documenting WHEN KIT_WORK_DOMAIN == unset AND ORIGINAL_INTENT primarily asks to create, edit, review, validate, or fix documentation, README files, guides, checklists, examples, or human-facing templates inside a kit
  SET KIT_WORK_DOMAIN = coding WHEN KIT_WORK_DOMAIN == unset AND ORIGINAL_INTENT primarily asks to create, edit, review, validate, or fix scripts, tests, generators, validators, utilities, or other executable code inside a kit
  SET KIT_WORK_DOMAIN = manifest WHEN KIT_WORK_DOMAIN == unset AND ORIGINAL_INTENT primarily asks to create, edit, normalize, validate, or fix `.cf-studio-kit.toml`, legacy kit manifests, resource registration, or kit layout/configuration metadata
  SET KIT_WORK_DOMAIN = mixed WHEN ORIGINAL_INTENT explicitly spans multiple kit asset domains, asks to update the kit broadly without a scoped asset type, or combines manifest work with prompt/doc/code work in one request
RULES:
  ALWAYS classify from explicit scoped target paths before falling back to free-text intent parsing
  ALWAYS prefer the narrowest specialist workflow that matches the scoped kit asset type
  ALWAYS classify broad "update the kit" or "edit the whole kit" requests as mixed unless the request clearly narrows the asset type
  NEVER let kit thin workflows duplicate prompt, document, or code authoring/review/CI logic that already exists in specialist workflows
```

```pdsl
UNIT KitThinRouteBlocked
PURPOSE: Return a visible blocked result when the kit request is mixed or not scoped enough for safe specialist delegation.
STATE:
  SET missing_artifacts: list | unset (default unset, scope workflow_run)
  SET suggested_next_skills: list | unset (default unset, scope workflow_run)
DO:
  SET missing_artifacts = kit-thin-scope with why_needed "This thin kit family only handles scoped prompt, document, or code work; mixed requests must be decomposed and manifest/config work must route through cf-kit", accepted_shapes narrowed-intent or phase-plan-doc or phase-plan-bundle, suggested_producers cf-kit, kit-planning, prompting-planning, documenting-planning, code-planning, explore, brainstorm, override_allowed false
  SET suggested_next_skills = cf-kit, kit-planning, explore, brainstorm WHEN KIT_WORK_DOMAIN == manifest
  SET suggested_next_skills = kit-planning, prompting-planning, documenting-planning, code-planning, explore, brainstorm WHEN KIT_WORK_DOMAIN == mixed OR KIT_WORK_DOMAIN == unset
  RUN BlockedReportContract
RULES:
  ALWAYS route manifest and kit-configuration work to cf-kit rather than pretending the kit thin prompt/doc/code family owns it
  ALWAYS direct mixed kit work toward planning before generation, review, CI, or fix execution
  NEVER guess a single specialist route when the request still spans multiple kit asset domains
```
