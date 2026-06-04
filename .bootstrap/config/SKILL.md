# Custom Skill Extensions

Add your project-specific skill instructions here.
These are loaded alongside the generated skills in `{cf-studio-path}/.gen/SKILL.md`.

## Documentation conventions

ALWAYS treat the repository root `README.md` as exempt from the Table-of-Contents requirement. It uses a manual `**Jump to:**` quick-navigation line instead of a generated `<!-- toc -->` block, because the curated quick links are preferred for the landing page.

NEVER add a `<!-- toc -->` block to `README.md`, and NEVER run `cfs validate-toc` against `README.md` or treat its missing TOC as a deterministic-gate failure. Other Markdown documents (guides, requirements, specs) still require a valid TOC.
