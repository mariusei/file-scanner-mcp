# M2b preregistered expectations (written BEFORE the first episode)

1. Concept/structure tasks: scantool agents at least as correct as grep
   agents, with >=2x fewer logged output tokens
2. The literal task (T4): ~tie
3. Overview (T5): possible grep win (as measured in the harness)
4. Open hypothesis: real agents REFORMULATE searches — may help both sides,
   effect unknown
5. Model choice: haiku subagents, deliberately — tool value should show
   most strongly for weaker models. Risk: instruction violations; mitigated
   by log verification (facts in the answer MUST exist in the log, otherwise
   invalid)
6. A null outcome is valid: if grep agents match scantool agents on
   correctness AND tokens, the information-delivery margin is not
   task-relevant — that would weaken the v1.0 claim
