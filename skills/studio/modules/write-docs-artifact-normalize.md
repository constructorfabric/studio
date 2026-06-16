# Write Docs Artifact Normalize
```pdsl
UNIT WriteDocsArtifactContextNormalize
PURPOSE: Normalize preset-bound artifact references into the payload field names required by author and artifact-reviewer contracts.
DO:
  RUN WriteDocsNormalizeArtifactKind
  RUN WriteDocsNormalizeArtifactTemplateAndRules
  RUN WriteDocsNormalizeArtifactChecklist
  RUN WriteDocsNormalizeArtifactExample
RULES:
  ALWAYS keep preset-bound artifact references as read-only payload fields
  NEVER invent artifact template, rules, checklist, or example paths when no preset supplied them
```
```pdsl
UNIT WriteDocsNormalizeArtifactKind
PURPOSE: Normalize the artifact kind into the review payload field.
DO:
  SET ARTIFACT_REVIEW_KIND = ARTIFACT_KIND WHEN ARTIFACT_KIND is set
  SET ARTIFACT_REVIEW_KIND = null WHEN ARTIFACT_REVIEW_KIND == unset
```
```pdsl
UNIT WriteDocsNormalizeArtifactTemplateAndRules
PURPOSE: Normalize preset-bound template and rules references.
DO:
  SET ARTIFACT_TEMPLATE_PATH = artifact_template WHEN artifact_template is set
  SET ARTIFACT_TEMPLATE_PATH = null WHEN ARTIFACT_TEMPLATE_PATH == unset
  SET ARTIFACT_RULES_PATH = artifact_rules WHEN artifact_rules is set
  SET ARTIFACT_RULES_PATH = null WHEN ARTIFACT_RULES_PATH == unset
```
```pdsl
UNIT WriteDocsNormalizeArtifactChecklist
PURPOSE: Normalize checklist references and whether checklist context is available.
DO:
  SET ARTIFACT_CHECKLIST_PATH = artifact_checklist WHEN artifact_checklist is set
  SET ARTIFACT_CHECKLIST_PATH = checklist_path WHEN ARTIFACT_CHECKLIST_PATH == unset AND checklist_path is set
  SET ARTIFACT_CHECKLIST_PATH = null WHEN ARTIFACT_CHECKLIST_PATH == unset
  SET ARTIFACT_CHECKLIST_CONTEXT = preset-bound WHEN ARTIFACT_CHECKLIST_PATH != null
  SET ARTIFACT_CHECKLIST_CONTEXT = unavailable WHEN ARTIFACT_CHECKLIST_PATH == null
```
```pdsl
UNIT WriteDocsNormalizeArtifactExample
PURPOSE: Normalize the preset-bound example reference.
DO:
  SET ARTIFACT_EXAMPLE_PATH = artifact_example WHEN artifact_example is set
  SET ARTIFACT_EXAMPLE_PATH = null WHEN ARTIFACT_EXAMPLE_PATH == unset
```
