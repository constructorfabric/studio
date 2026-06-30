# Commit Policy Load

```pdsl
UNIT CommitPolicyLoadContract
PURPOSE: Load the shared commit-policy source set without performing a commit.
STATE:
  SET COMMIT_POLICY_SOURCES: list | unset (default unset, scope unit_run)
  SET GIT_COMMIT_MODE: commit | stage | none | unset (default unset, scope unit_run)
DO:
  RUN CommitPolicySourceContract
  RUN CommitPolicyModeContract
RULES:
  ALWAYS use this module only to collect commit-related policy inputs for later validation or delegation
  ALWAYS keep commit policy sources machine-readable and source-oriented
  NEVER treat policy loading as permission to finalize a commit
```

```pdsl
UNIT CommitPolicySourceContract
PURPOSE: Define the shared source registry for commit-related policy inputs.
RULES:
  ALWAYS allow COMMIT_POLICY_SOURCES to contain zero-or-more entries for project-rules, contributing-guide, trailer-requirements, and commit-mode
  ALWAYS represent each COMMIT_POLICY_SOURCES entry with source_type, ref, and summary
  ALWAYS keep source_type explicit even when multiple policy inputs live in one file
  ALWAYS preserve missing policy sources as an explicit absence instead of fabricating defaults in this module
  NEVER hardcode workflow-local commit rules into this loader contract
```

```pdsl
UNIT CommitPolicyModeContract
PURPOSE: Keep git commit mode explicit when policy inputs define one.
RULES:
  ALWAYS allow GIT_COMMIT_MODE to be unset when no policy source defines it
  ALWAYS require GIT_COMMIT_MODE to come from an explicit policy source when it is set
  ALWAYS keep GIT_COMMIT_MODE separate from commit intent, approval, and execution state
  NEVER infer commit permission from GIT_COMMIT_MODE alone
```
