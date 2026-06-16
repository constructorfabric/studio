# Kit Discovery Classify
```pdsl
UNIT KitInitDiscoveryClassifyCandidates
PURPOSE: Load the discovery context and classify candidate resources before proposal synthesis.
DO:
  RUN ResourceContextMemory
  RUN classify candidates from RESOURCE_CONTEXT into public skills, agents, and rules, plus supporting templates, checklists, scripts, directories, and other
UNIT KitInitDiscoveryBindArtifacts
PURPOSE: Derive explicit artifact-kind bindings for discovered constraints resources before manifest synthesis.
DO:
  RUN derive explicit artifact-kind bindings for every constraints resource from RESOURCE_CONTEXT evidence:
    - template/checklist/rules/example files are bound to artifact kinds only when the kind is explicit in file metadata, constraints kind names, or an unambiguous per-kind layout such as `artifacts/<KIND>/template.md`
    - bindings point to resource IDs, never filesystem paths
    - ambiguous files remain unbound and are reported as ambiguities
```
