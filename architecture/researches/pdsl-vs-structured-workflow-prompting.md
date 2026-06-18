# PDSL vs. Research Findings on Structured Workflow Prompting

## Purpose

This note compares the current PDSL specification against findings from research
on finite-state prompting, structured prompting, and LLM workflow orchestration.
The goal is to assess how closely PDSL matches the formats and control
mechanisms that the literature suggests are effective for turning reusable
skills into reliable workflows.

## Sources

Scientific sources used in this note:

1. Wang et al., **FSM: A Finite State Machine Based Zero-Shot Prompting Paradigm for Multi-Hop Question Answering** (arXiv, 2024)  
   https://arxiv.org/abs/2407.02964
2. Sultan et al., **Structured Chain-of-Thought Prompting for Few-Shot Generation of Content-Grounded QA Conversations** (arXiv, 2024)  
   https://arxiv.org/abs/2402.11770
3. Fan et al., **WorkflowLLM: Enhancing Workflow Orchestration Capability of Large Language Models** (arXiv, 2024)  
   https://arxiv.org/abs/2411.05451
4. White et al., **A Prompt Pattern Catalog to Enhance Prompt Engineering with ChatGPT** (arXiv, 2023)  
   https://arxiv.org/abs/2302.11382
5. Lu et al., **Learning to Generate Structured Output with Schema Reinforcement Learning** (arXiv, 2025)  
   https://arxiv.org/abs/2502.18878

## Comparison Table

| Criterion | What research suggests | What PDSL provides | Assessment |
| --- | --- | --- | --- |
| Explicit decomposition of complex tasks | Break complex work into local steps or states instead of one large prompt. Supported by FSM prompting and structured CoT work. | `UNIT`, `WHEN`, `DO`, `RUN`, `CONTINUE` provide explicit decomposition into smaller executable units. | Strong alignment |
| FSM-like control flow | Effective prompting for complex tasks benefits from explicit states, branches, continuation logic, and stop points. | `STATE`, `WHEN`, `WAIT`, `STOP_TURN`, `CONTINUE`, and `MENU` provide explicit control flow. | Strong alignment |
| Localized instructions per state | Each state should have its own focused instructions and resources. | Each `UNIT` acts as a local handler with its own conditions, actions, and rules. | Strong alignment |
| Explicit interaction states | User-facing branches should be part of the workflow model, not hidden in prose. | `MENU`, `OPTIONS`, `INVALID`, `WAIT`, and `STOP_TURN` make interaction states first-class. | Strong alignment |
| Declarative workflow expression | Structured, declarative workflow descriptions are easier to follow and orchestrate than narrative prompts. | PDSL is a compact declarative notation for workflow behavior. | Strong alignment |
| Reusable prompting patterns | Reusable prompt patterns improve consistency and reduce ambiguity. | PDSL promotes reusable `UNIT`s, shared runtime modules, and `PATTERNS`. | Good alignment |
| Workflow orchestration readiness | Orchestration benefits from explicit handoffs, phases, and execution ownership. | `RUN`, `DISPATCH`, `RETURN`, bootstrap units, and workflow modules support orchestration. | Good alignment |
| Error handling and recovery | Complex workflows benefit from explicit recovery paths and controlled iteration. | `ON_ERROR` exists and allows explicit recovery routing. | Good alignment |
| Explicit transition contract | Research directions imply value in clear `current state -> condition -> next state` representations. | Transitions exist, but are distributed across `WHEN`, `DO`, and `CONTINUE`; there is no dedicated transition construct. | Partial gap |
| Typed state model | More formal workflow systems benefit from clearly typed and constrained state/data models. | `STATE` can declare allowed values and defaults, but remains mostly textual and lightweight. | Partial gap |
| Strict output contract | Reliable workflow execution increasingly depends on machine-checkable outputs, often schema-bound. | `RETURN` describes a handoff, but PDSL does not define a strict structured output contract. | Significant gap |
| Schema-bound execution results | Structured output research shows reliability improves when outputs must satisfy explicit schemas. | PDSL does not embed JSON-schema-like result validation for state decisions or returns. | Significant gap |
| Semantic validation | Strong workflow DSLs validate references, state usage, transitions, and constraints semantically, not just syntactically. | Current PDSL validation is mainly structural. | Significant gap |
| Enforced authoring limits | If compactness rules are part of the spec, validators should enforce them. | The spec defines limits such as max `DO` actions and max `RULES`, but current validation does not appear to enforce them. | Spec/implementation gap |
| Shared pattern registry enforcement | Reusable pattern registries should be recognized by validators. | The spec allows local and canonical pattern registries, but current validation appears focused on local definitions. | Spec/implementation gap |
| Deterministic control interpretation | Execution semantics should be explicit enough that controllers interpret the workflow consistently. | PDSL defines runtime semantics and a shared execution card for controllers. | Good alignment |
| Separation of behavior from prose | Effective prompting benefits from separating executable behavior from explanatory narrative. | PDSL explicitly reserves prose for rationale and PDSL for behavior. | Strong alignment |

## Summary

PDSL aligns well with the strongest recurring research finding: workflow-like
prompting works better when behavior is decomposed into explicit states,
branches, local instructions, and stop boundaries rather than embedded in long
free-form prose.

Its strongest matches to the literature are:

- explicit stateful decomposition
- clear branching and continuation semantics
- reusable local workflow units
- first-class interaction states
- declarative control flow instead of narrative prompting

Its main gaps relative to stricter workflow-oriented approaches are:

- no first-class transition object
- no built-in schema-bound output contract
- limited semantic validation
- partial mismatch between the written spec and validator behavior

## Practical Conclusion

PDSL is already close to a strong **structured workflow prompting DSL** for
LLM-controlled skills and workflows. It is much closer to research-backed
best practice than ordinary prose prompts.

However, it is not yet a fully strict workflow contract language. To move
closer to the strongest reliability-oriented findings in the literature, the
next improvements would be:

1. add an explicit transition/result contract such as `next_state`, `action`,
   `arguments`, and `done`
2. support schema-bound outputs for unit decisions and returns
3. extend validation from structural checks to semantic checks over state,
   references, transitions, and registry-backed patterns
