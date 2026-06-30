# Commit Trailer Prepare

```pdsl
UNIT CommitTrailerPrepareContract
PURPOSE: Prepare required Studio and project commit trailers in a machine-readable form.
STATE:
  SET COMMIT_TRAILER_REQUIREMENTS: list | unset (default unset, scope unit_run)
  SET PREPARED_COMMIT_TRAILERS: list | unset (default unset, scope unit_run)
  SET COMMIT_FOOTER_CONTRACT: object | unset (default unset, scope unit_run)
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/commit-policy-load.md WHEN CommitPolicyLoadContract is not yet loaded
  RUN CommitTrailerRequirementContract
  RUN CommitTrailerRecordContract
RULES:
  ALWAYS use this module only to prepare trailer data for later commit authoring or validation
  ALWAYS keep prepared trailers machine-readable instead of assembling a final commit message body here
  NEVER let this module finalize, sign, or submit a commit
```

```pdsl
UNIT CommitTrailerRequirementContract
PURPOSE: Define the minimum input contract for required trailers.
DO:
  SET COMMIT_TRAILER_REQUIREMENTS = trailer requirements derived from COMMIT_FOOTER_CONTRACT.required_trailers and COMMIT_FOOTER_CONTRACT.optional_trailers, preserving order, token as trailer_key, required-ness, and source_ref = COMMIT_FOOTER_CONTRACT.authority WHEN COMMIT_TRAILER_REQUIREMENTS == unset AND COMMIT_FOOTER_CONTRACT is provided
RULES:
  ALWAYS require COMMIT_TRAILER_REQUIREMENTS to be an explicit list when trailer policy exists
  ALWAYS represent each requirement with trailer_key, required, and source_ref
  ALWAYS allow optional trailer_template and trailer_value_hint fields
  ALWAYS keep trailer requirements independent from the eventual commit message formatting
  NEVER hide required trailer keys only in narrative policy prose once this module is active
```

```pdsl
UNIT CommitTrailerRecordContract
PURPOSE: Define the prepared trailer payload for downstream commit validation.
DO:
  SET PREPARED_COMMIT_TRAILERS = entries derived from COMMIT_TRAILER_REQUIREMENTS, preserving order, with trailer_key, trailer_value from an explicit requirement value when present else unset, required, and source_ref
RULES:
  ALWAYS represent each PREPARED_COMMIT_TRAILERS entry with trailer_key, trailer_value, required, and source_ref
  ALWAYS preserve requirement ordering when the caller supplies one
  ALWAYS allow trailer_value to remain unset only when required == false or a later step is expected to fill it explicitly
  ALWAYS keep prepared trailer entries shallow and deterministic
  NEVER encode commit execution results into prepared trailer records
```
