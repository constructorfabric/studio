# CI Discovery Run
```pdsl
UNIT CiDiscoveryRunStart
PURPOSE: Gate CI skills by discovering relevant CI targets and available CI tools via cf-explore before any CI gate command is resolved.
STATE:
  CI_DISCOVERY_INTENT: ci-coding | ci-documenting | ci-prompting  # required; set by the calling CI skill before loading this module
  REVIEW_TARGET_PATHS: list | unset                                # populated by discovery or supplied by caller
  CI_DISCOVERY_STATUS: provided | empty | skipped | error | unset  # unset by default
  CI_TOOL_SOURCES: list | unset                                    # paths of discovered CI tool definition files; populated by CiToolSourcesProbe
WHEN:
  REQUIRE CI_DISCOVERY_INTENT is set
DO:
  IF REVIEW_TARGET_PATHS is already provided THEN
    SET CI_DISCOVERY_STATUS = provided
    CONTINUE CiDiscoveryRunClassifyResult
  ELSE
    EMIT_MENU CiDiscoverySkipMenu
    WAIT user.reply
    STOP_TURN
  IF user chose option 2 (skip) THEN
    SET CI_DISCOVERY_STATUS = skipped
    CONTINUE CiDiscoveryRunClassifyResult
  ELSE
    RUN CiToolSourcesProbe
    INVOKE skill `cf-explore` with intent="discover CI targets and all available CI tools (linting, testing, formatting, type-checking, deterministic validation) for CI_DISCOVERY_INTENT" and return_context=true, scoped to project root, known_paths = union of project root and CI_TOOL_SOURCES
    SET REVIEW_TARGET_PATHS from cf-explore result resource_context
    CONTINUE CiDiscoveryRunClassifyResult
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
  1 discover -> run CiToolSourcesProbe then cf-explore to find CI targets and available tools, then continue
  2 skip -> skip discovery; use caller-supplied REVIEW_TARGET_PATHS or inline heuristic
  INVALID -> EMIT_MENU CiDiscoverySkipMenu

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
  SET CI_DISCOVERY_STATUS = provided WHEN CI_DISCOVERY_STATUS == provided
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
  2 provide -> EMIT "Reply with the REVIEW_TARGET_PATHS you want to use (one path per line)."; WAIT user.reply; SET REVIEW_TARGET_PATHS from user reply; CONTINUE CiDiscoveryRunClassifyResult
  3 stop -> STOP_TURN and return blocked to the calling CI skill
  INVALID -> EMIT_MENU CiDiscoveryFailureMenu
```
