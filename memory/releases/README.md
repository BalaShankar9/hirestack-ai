# memory/releases

Per-release notes. Lighter-weight than CHANGELOG entries — these
capture *the experience* of shipping, not just what changed.

- **Importance**: 2.5
- **Naming**: `<YYYY-MM-DD>-v<X.Y.Z>.md` or `<YYYY-MM-DD>-<sprint-name>.md`

## Write contract

```markdown
# Release <version> — <YYYY-MM-DD>

- **PR range**: #NN through #NN
- **Driver**: <person / team>

## What shipped
- bullets, with PR links

## What we learned
<Process / tooling / coordination lessons. The kind of thing that
goes into a sprint retro but disappears after.>

## What broke (if anything)
<Link to incident notes if applicable.>

## Validation
<Smoke results, prod metrics for first 24h.>

## Linked
- incident notes
- CHANGELOG link
```
