# PresentationOrchestrator Architecture

Professional-grade pipeline-based presentation generation.

## Architecture

### Phase Protocols (Interfaces)

```
PlanningPhase              -> Generates DeckSpec from topic
DeckTransformPhase         -> Transforms DeckSpec (before composition)
CompositionPhase          -> DeckSpec -> PPTX bytes
PostProcessPhase          -> Transforms PPTX bytes (after composition)
```

### Phase Implementations

| Phase | Class | Responsibility |
|-------|-------|----------------|
| 0 | `OutlineGenerationPhase` | AI outline generation |
| 3 | `DataResearchPhase` | Real data enrichment |
| 8 | `QualityValidationPhase` | Quality scoring & auto-revision |
| 9 | `AIImageGenerationPhase` | Custom AI visuals |
| 10 | `ContentEnhancementPhase` | AI-optimized text |
| 1 | `PresentationCompositionPhase` | Render to PPTX |
| 7 | `PolishPhase` | Accessibility & polish |
| 11 | `InteractiveElementsPhase` | TOC, navigation |
| 12 | `TranslationPhase` | Multi-language support |

## Usage

### Factory Method (Recommended)

```python
from ai_engine.agents.ppt import PresentationOrchestrator

orch = PresentationOrchestrator.create_with_defaults(
    enable_data_research=True,
    enable_content_enhancement=True,
    enable_ai_images=True,
    enable_interactive=True,
    target_language="es",
)

result = await orch.generate(topic="AI Trends")

print(result.quality_score)    # 0.85
print(result.metadata)         # {"data_research": True, ...}
```

### Custom Pipeline

```python
from ai_engine.agents.ppt.orchestrator import (
    PresentationOrchestrator,
    OutlineGenerationPhase,
    DataResearchPhase,
    PresentationCompositionPhase,
)

orch = PresentationOrchestrator(
    outline_phase=OutlineGenerationPhase(),
    data_research=DataResearchPhase(enabled=True),
    composition=PresentationCompositionPhase(),
)
```

## Design Principles

1. **Single Responsibility**: Each phase handles one concern
2. **Open/Closed**: New phases without modifying existing code
3. **Dependency Inversion**: Phases depend on protocols, not implementations
4. **Composition**: Pipeline assembled from phase components

## Error Handling

- Phase failures are logged but don't stop pipeline (graceful degradation)
- Critical failures (outline, composition) raise exceptions
- Quality validation auto-revises if score < threshold

## Backward Compatibility

```python
from ai_engine.agents.ppt import PPTOrchestrator, PPTResult

# Old API still works
orch = PPTOrchestrator()
result = await orch.generate(topic="...")
```

Both are aliases to `PresentationOrchestrator` and `GenerationResult`.
