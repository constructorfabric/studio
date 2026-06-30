# CI Discovery Run
```pdsl
UNIT CiDiscoveryRunStart
PURPOSE: Gate CI skills by discovering relevant CI targets and available CI tools via cf-explore before any CI gate command is resolved.
STATE:
  CI_DISCOVERY_INTENT: ci-coding | ci-documenting | ci-prompting  # required; set by the calling CI skill before loading this module
  REVIEW_TARGET_PATHS: list | unset                                # populated by discovery or supplied by caller
  CI_DISCOVERY_STATUS: provided | empty | skipped | error | unset  # unset by default
  CI_TOOL_SOURCES: list | unset                                    # paths of discovered CI tool definition files; populated by CiToolSourcesProbe
  CI_TARGET_CAPTURE_STATE: resume | unset                          # set while waiting for manually provided targets
WHEN:
  REQUIRE CI_DISCOVERY_INTENT is set
DO:
  CONTINUE CiDiscoveryProvideTargetsResume WHEN CI_TARGET_CAPTURE_STATE == resume
  SET CI_DISCOVERY_STATUS = provided WHEN REVIEW_TARGET_PATHS is already provided
  CONTINUE CiDiscoveryRunClassifyResult WHEN CI_DISCOVERY_STATUS == provided
  EMIT_MENU CiDiscoverySkipMenu
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS require the calling CI skill to SET CI_DISCOVERY_INTENT before loading this module
  ALWAYS run CiToolSourcesProbe before invoking cf-explore so that CI definition files are included in known_paths
  ALWAYS skip discovery and proceed directly when REVIEW_TARGET_PATHS is already caller-supplied
  ALWAYS present the explicit skip menu when discovery is about to run and REVIEW_TARGET_PATHS is unset
  ALWAYS populate REVIEW_TARGET_PATHS from the cf-explore result before returning to the calling CI skill
  NEVER silently fall back to inline heuristics when discovery is empty — use the failure menu
  NEVER run cf-explore in write or mutate mode
MENU CiDiscoverySkipMenu
TITLE: CI discovery — find relevant CI targets automatically or skip?
OPTIONS:
  1 discover -> CONTINUE CiDiscoveryRunExecute
  2 skip -> SET CI_DISCOVERY_STATUS = skipped; CONTINUE CiDiscoveryRunClassifyResult
  INVALID -> EMIT_MENU CiDiscoverySkipMenu

UNIT CiDiscoveryRunExecute
PURPOSE: Run CiToolSourcesProbe then invoke cf-explore to populate REVIEW_TARGET_PATHS.
DO:
  RUN CiToolSourcesProbe
  INVOKE skill `cf-explore` with intent="discover CI targets and all available CI tools (linting, testing, formatting, type-checking, deterministic validation) for CI_DISCOVERY_INTENT" and return_context=true, scoped to project root, known_paths = union of project root and CI_TOOL_SOURCES
  SET CI_DISCOVERY_STATUS = error WHEN cf-explore invocation fails
  CONTINUE CiDiscoveryRunFailure WHEN CI_DISCOVERY_STATUS == error
  SET REVIEW_TARGET_PATHS from cf-explore result resource_context
  CONTINUE CiDiscoveryRunClassifyResult

UNIT CiToolSourcesProbe
PURPOSE: Scan the project root for well-known CI tool definition files and populate CI_TOOL_SOURCES so cf-explore reads them during discovery.
STATE:
  CI_TOOL_SOURCES: list | unset  # set by this unit; unset before first run
DO:
  RUN scan project root for CI tool definition files matching any of:
    - Makefile, GNUmakefile, makefile
    - CONTRIBUTING.md, CONTRIBUTING.rst, CONTRIBUTING
    - README.md, README.rst, README
    - pyproject.toml, setup.cfg, tox.ini, .pre-commit-config.yaml
    - package.json, package-lock.json (scripts section only)
    - .github/workflows/ (all *.yml and *.yaml files under this directory)
    - .gitlab-ci.yml, .circleci/config.yml, Jenkinsfile, .travis.yml, azure-pipelines.yml
    - {cf-studio-path}/config/rules/build-deploy.md (project rules build/deploy guide)
    - any other file at project root whose name matches *CI*, *ci*, *lint*, *test*, *check*, *build* with a recognised extension (.md, .toml, .yaml, .yml, .json, .cfg, .ini, .sh)
  SET CI_TOOL_SOURCES = all paths found by the scan above that exist in the project
  SET CI_TOOL_SOURCES = [] WHEN no matching paths are found
RULES:
  ALWAYS populate CI_TOOL_SOURCES before cf-explore is invoked by CiDiscoveryRunStart
  ALWAYS include CONTRIBUTING files when present — they document project-specific test and lint commands
  ALWAYS include README when present — it may describe how to run CI locally
  ALWAYS include all CI platform config files found (GitHub Actions, GitLab CI, CircleCI, Travis, Jenkins, Azure Pipelines)
  ALWAYS include the project rules build-deploy guide when it exists under {cf-studio-path}/config/rules/
  ALWAYS keep CI_TOOL_SOURCES as a path list only; never read or inline file contents from this unit
  NEVER block or fail when no CI tool definition files are found; set CI_TOOL_SOURCES = [] and continue

UNIT CiDiscoveryRunClassifyResult
PURPOSE: Classify the discovery or skip outcome and determine whether to proceed or escalate to failure handling.
DO:
  SET CI_DISCOVERY_STATUS = provided WHEN CI_DISCOVERY_STATUS == skipped AND REVIEW_TARGET_PATHS is provided
  RETURN to calling CI skill WHEN CI_DISCOVERY_STATUS == provided
  SET CI_DISCOVERY_STATUS = empty WHEN CI_DISCOVERY_STATUS == skipped AND REVIEW_TARGET_PATHS is unset
  CONTINUE CiDiscoveryRunFailure WHEN CI_DISCOVERY_STATUS == empty
  CONTINUE CiDiscoveryRunFailure WHEN CI_DISCOVERY_STATUS == error

UNIT CiDiscoveryRunFailure
PURPOSE: Emit a failure context message and present the failure menu when no CI targets were found or discovery failed.
DO:
  EMIT "CI discovery found no targets (CI_DISCOVERY_STATUS=${CI_DISCOVERY_STATUS}). REVIEW_TARGET_PATHS is unset. You must retry discovery, provide paths manually, or stop."
  EMIT_MENU CiDiscoveryFailureMenu
  WAIT user.reply
  STOP_TURN

MENU CiDiscoveryFailureMenu
TITLE: CI discovery found no targets. Choose how to proceed.
OPTIONS:
  1 retry -> SET CI_DISCOVERY_STATUS = unset; CONTINUE CiDiscoveryRunStart
  2 provide -> SET CI_TARGET_CAPTURE_STATE = resume; EMIT "Reply with the REVIEW_TARGET_PATHS you want to use (one path per line)."; WAIT user.reply; STOP_TURN
  3 stop -> STOP_TURN and return blocked to the calling CI skill
  INVALID -> EMIT_MENU CiDiscoveryFailureMenu

UNIT CiDiscoveryProvideTargetsResume
PURPOSE: Resume CI discovery after the user manually supplies target paths.
WHEN:
  REQUIRE CI_TARGET_CAPTURE_STATE == resume
  REQUIRE user.reply exists
DO:
  SET REVIEW_TARGET_PATHS = file paths parsed from user.reply WHEN user.reply names one or more files
  SET CI_TARGET_CAPTURE_STATE = unset WHEN REVIEW_TARGET_PATHS is provided
  CONTINUE CiDiscoveryRunClassifyResult WHEN REVIEW_TARGET_PATHS is provided
  CONTINUE CiDiscoveryRunFailure WHEN REVIEW_TARGET_PATHS is unset
```
