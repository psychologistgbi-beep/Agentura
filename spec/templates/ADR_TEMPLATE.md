# ADR-NN: <Title>

**Status:** Proposed | Accepted | Deprecated | Superseded by ADR-XX

**Date:** YYYY-MM-DD

---

## Context

What is the issue that we're seeing that is motivating this decision or change?
What are the constraints and forces at play?

## Decision

What is the change that we're proposing and/or doing?
State the decision clearly and unambiguously.

## Consequences

What becomes easier or more difficult to do because of this change?
Include both positive and negative consequences.

### Positive
- ...

### Negative
- ...

## Alternatives considered

| Alternative | Pros | Cons | Why rejected |
|---|---|---|---|
| Option A | ... | ... | ... |
| Option B | ... | ... | ... |

## Rollback

How to reverse this decision if it proves wrong:
1. ...
2. ...
3. ...

What data migration or cleanup is needed on rollback?

## Verification

Commands or checks that prove the decision is correctly implemented:

```bash
# Example
cd apps/executive-cli
rm -f .data/execas.sqlite && uv run execas init
uv run pytest -q
```

## References

- Related ADRs: ADR-XX
- Spec sections: TECH_SPEC.md section Y
- External: [link](url)
