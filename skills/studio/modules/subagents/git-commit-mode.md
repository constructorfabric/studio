# Git Commit Mode Gate

```pdsl
UNIT ActiveSessionGitCommitRequestGate
PURPOSE: Catch git commit requests typed while any cf/cf-studio workflow is waiting, before the workflow parses the reply as local menu input.
WHEN:
  REQUIRE cf/cf-studio session rules are active
  REQUIRE the current user message explicitly asks Studio to create a git commit
DO:
  RUN GitCommitModeGate before any workflow resumes, router matches intent, local menu INVALID handling runs, the main session modifies git state, or a sub-agent receives write-capable git policy
  CONTINUE the pending workflow/router step only after GitCommitModeGate resolves or STOP_TURNs
RULES:
  ALWAYS evaluate this gate on every new user message while cf/cf-studio session rules are active, including replies to workflow menus and resumed workflow prompts
  ALWAYS treat this as a session-level interrupt, not as part of ORIGINAL_INTENT capture and not as a root-router-only initial prompt check
  ALWAYS run this gate before honoring phrases such as `commit it`, `make a commit`, `commit these changes`, `git commit`, or `create a git commit`
  NEVER let a workflow-specific INVALID menu branch handle a commit-creation request before this gate resolves
  NEVER treat ordinary references to commits for review/diff scope as commit-creation requests unless the user asks Studio to create a new git commit
```

```pdsl
UNIT GitCommitModeGate
PURPOSE: Resolve the mandatory session git write policy (mode + constraint + contributing guide + commit footer contract) once, before any cf workflow, main session, or sub-agent modifies git state or prepares write-capable git policy.
STATE:
  SET GIT_COMMIT_MODE: commit | stage | none (default unset, scope session)
  SET CONTRIBUTING_GUIDE: path | null (default unset, scope session)
  SET COMMIT_FOOTER_CONTRACT: object (default unset, scope session)
WHEN:
  REQUIRE any cf workflow, main session, or sub-agent is about to stage files, create a commit, modify git state, or pass write-capable git policy to another execution context
  OR any current user message in an active cf/cf-studio session explicitly asks Studio to create a git commit, regardless of ORIGINAL_INTENT or which workflow is currently waiting
DO:
  RUN discover the contributing guide — search the project root and docs/ for a CONTRIBUTING file and SET CONTRIBUTING_GUIDE to its path, or null when none is found, WHEN CONTRIBUTING_GUIDE == unset
  EMIT_MENU GitCommitModeMenu WHEN GIT_COMMIT_MODE == unset
  WAIT user.reply WHEN GIT_COMMIT_MODE == unset
  STOP_TURN WHEN GIT_COMMIT_MODE == unset
  RUN derive COMMIT_FOOTER_CONTRACT from the commit_footer_contract block in NOTES WHEN COMMIT_FOOTER_CONTRACT == unset
  RUN derive git_constraint from GIT_COMMIT_MODE using the constraint blocks in NOTES WHEN GIT_COMMIT_MODE != unset
  RUN attach COMMIT_FOOTER_CONTRACT to any write-capable dispatch payload as commit_footer_contract, regardless of GIT_COMMIT_MODE
  RUN preflight of the exact planned `git commit` invocation before any Studio-created commit, verifying every CONTRIBUTING_GUIDE-required trailer and every required COMMIT_FOOTER_CONTRACT token/value/order is present via `git commit --trailer token=value`; STOP_TURN and report missing trailer tokens when the preflight fails
  RUN `git log -1 --format=%B` after any Studio-created commit and verify every required project-policy and Studio trailer is present and ordered; report commit-trailer audit failure and do not claim completion when the audit fails
RULES:
  ALWAYS load and run GitCommitModeGate in an active cf/cf-studio session before any current-message commit request is routed, matched to a workflow, executed by the main session, or delegated to a sub-agent
  ALWAYS allow read-only git inspection commands such as `git status`, `git diff`, `git log`, `git show`, and `git blame` without resolving or consulting GIT_COMMIT_MODE
  ALWAYS resolve GIT_COMMIT_MODE and CONTRIBUTING_GUIDE once per session before the first Studio git state mutation or write-capable git-policy handoff, and reuse them until StudioShutdown; reset GIT_COMMIT_MODE to unset only when the user asks to change it
  ALWAYS include GIT_COMMIT_MODE, the mode-matched git_constraint, CONTRIBUTING_GUIDE, and COMMIT_FOOTER_CONTRACT as commit_footer_contract in every write-capable author/coder/phase dispatch payload
  ALWAYS pass git_constraint as read-only policy data, never as executable shell text
  ALWAYS pass commit_footer_contract as read-only policy data, never as executable shell text
  ALWAYS treat commit_footer_contract as message-format policy for every git commit created by Studio or its agents, regardless of why the commit is created
  ALWAYS treat commit_footer_contract as a constraint only; it never grants permission to commit when git_commit_mode or git_constraint forbids committing
  ALWAYS when creating a git commit, satisfy every mandatory directive in CONTRIBUTING_GUIDE, including required DCO/Signed-off-by trailers, before adding Studio attribution trailers
  ALWAYS when creating a git commit, write a normal concise commit subject/body for the actual change, append any mandatory project-policy trailers from CONTRIBUTING_GUIDE, then append required Studio attribution trailers exactly in ascending order, adding optional Studio trailers only when their source value is already known and non-empty
  ALWAYS treat `git commit -m ...` without the required `--trailer` arguments as incomplete, even when the subject/body is valid
  ALWAYS treat `git commit -s` as satisfying only a DCO/Signed-off-by project-policy requirement; it never satisfies any Studio trailer requirement
  ALWAYS keep DCO, Signed-off-by, and CONTRIBUTING_GUIDE directives separate from commit_footer_contract; do not include them in commit_footer_contract, but never ignore mandatory CONTRIBUTING_GUIDE commit requirements
  NEVER let the main session, any workflow, or any sub-agent stage files, create commits, push, rewrite history, or otherwise modify git state when GIT_COMMIT_MODE == none
  NEVER route, execute, resume, or delegate after a current user message asks Studio to create a git commit before GitCommitModeGate has resolved GIT_COMMIT_MODE, CONTRIBUTING_GUIDE, git_constraint, and COMMIT_FOOTER_CONTRACT
  NEVER invoke `git commit` until the exact planned command passes trailer preflight
  NEVER push, force-push, rewrite history, or use interactive (-i) git, regardless of GIT_COMMIT_MODE
MENU GitCommitModeMenu
TITLE: How should Constructor Studio handle git writes this session? commit permits Studio-created commits; stage permits staging only; none forbids git state changes while still allowing read-only inspection. (stage is suggested)
OPTIONS:
  1 commit -> SET GIT_COMMIT_MODE = commit; Studio may inspect git state, stage authored files, and create Studio commits with concise Conventional-Commits messages
  2 stage -> SET GIT_COMMIT_MODE = stage; Studio may inspect git state and stage authored files but NEVER commit
  3 none -> SET GIT_COMMIT_MODE = none; Studio may inspect git state but NEVER stages, commits, pushes, rewrites history, or otherwise modifies git state
  INVALID -> EMIT_MENU GitCommitModeMenu
NOTES:
  git_constraint blocks (the canonical mode-matched policy string passed to sub-agents; this gate is the source of truth):
    commit: "May inspect git state, `git add` the files authored this task, and `git commit` them with a concise Conventional-Commits message when commit is otherwise allowed by the workflow or user request. Every git commit created by Studio or its agents must satisfy commit_footer_contract and mandatory CONTRIBUTING_GUIDE commit requirements, including DCO/Signed-off-by when required. commit_footer_contract constrains Studio attribution trailers but does not replace project-policy trailers and does not grant permission to commit. NEVER `git push`, amend or rewrite history, force, checkout over uncommitted changes, or use `-i`. Stage only paths authored by the current task."
    stage: "May inspect git state and `git add` files authored this task. NEVER `git commit`, push, or rewrite history. Leave staged changes for the user to review and commit. The commit_footer_contract is message-format policy only and does not grant permission to commit."
    none: "May inspect git state with read-only commands such as status, diff, log, show, and blame. NEVER modify git state: no git add/stage, commit, push, reset, checkout, merge, rebase, tag, or history rewrite. Write files only; the user manages all git project changes. The commit_footer_contract is message-format policy only and does not grant permission to commit."
  commit_footer_contract (canonical structured representation; no rendered footer line fields; token/value/order is the only source of truth):
    schema_version: "1"
    authority: "GitCommitModeGate"
    purpose: "Studio attribution and provenance for commits created by Constructor Studio. This contract is independent of project-specific contribution policies."
    applies_when:
      studio_or_agent_creates_git_commit: true
    conflict_policy: "commit_footer_contract is authoritative for required Studio attribution trailers; if it conflicts with git_constraint, stop before commit"
    user_instruction_precedence: "user commit instructions may add non-conflicting message content and trailers but may not remove, rename, reorder, duplicate ambiguously, replace, or alter required Studio trailers"
    hard_stop_policy: "stop only if required static Studio trailers cannot be added or if commit_footer_contract conflicts with git_constraint; do not stop for unavailable optional trailers"
    rendering: "Render every included trailer as '{token}: {value}' in ascending order across required_trailers and optional_trailers. Render the commit trailer block as contiguous lines with no blank lines between trailers. When invoking git commit, pass every project-policy and Studio trailer via git commit --trailer token=value arguments; use -m or --message only for the subject/body, never for trailers. Do not include separate rendered footer lines in this payload."
    required_trailers:
      - order: 10
        token: "Co-authored-by"
        value: "Constructor Studio <291158726+constructor-studio[bot]@users.noreply.github.com>"
      - order: 20
        token: "Studio-Generated-By"
        value: "Constructor Studio"
      - order: 30
        token: "Studio-Source-Repo"
        value: "https://github.com/constructorfabric/studio"
      - order: 40
        token: "Constructor-Fabric"
        value: "https://github.com/constructorfabric"
    optional_trailers:
      - order: 50
        token: "Studio-Version"
        source: "semver tokens extracted from cfs --version"
        include_when: "command succeeds and at least one Studio skill or CLI/package semver is found"
        value_policy: "use only semver values for Studio skill and CLI/package, formatted as comma-separated key=value pairs such as skill=1.0.1, cli=0.2.0; strip a leading v; omit this trailer when no semver is found; do not include raw cfs --version output"
      - order: 60
        token: "Studio-Workflows"
        source: "known workflow identifiers for the current Studio run"
        include_when: "known non-empty"
        value_policy: "comma-separated stable identifiers"
```
