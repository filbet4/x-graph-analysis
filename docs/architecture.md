# Architecture Notes

This document records architectural decisions for the thesis application.

## Dependency direction

The `domain` package owns stable models and ports. The `application` package coordinates those ports. Concrete adapters implement ports and are selected by the composition root in `main.py`.

```text
external sources -> adapters -> domain models -> application pipeline
                                      |
                  graph / analysis / visualization / reporting ports
```

This keeps source-specific concerns out of analysis modules and leaves room for local files, other APIs, or synthetic datasets.

TODO: Record decisions about graph semantics, persistence, privacy, API terms, and reproducibility.
