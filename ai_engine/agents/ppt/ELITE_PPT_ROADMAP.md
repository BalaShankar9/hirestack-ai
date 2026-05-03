# Elite PPT Agent Implementation Roadmap

## Objective
Transform the existing PPT agent from MVP to elite professional grade - producing presentations that rival top-tier design agencies.

## Phase 1: Native Editable Charts (CRITICAL) ✅ COMPLETE
**Status**: DONE  
**Goal**: Replace matplotlib PNGs with native PowerPoint charts that users can edit.

### Deliverables
- [x] `native_chart_renderer.py` - python-pptx Chart integration
- [x] Support: Bar, Column, Line, Pie, Scatter, Bubble natively
- [x] Data embedding in PPTX (Excel-like data tables)
- [x] Chart styling matching themes
- [x] Fallback to PNG only when native fails

### Technical Approach
- Use `pptx.chart.data.CategoryChartData` for bar/column/line
- Use `pptx.chart.data.XyChartData` for scatter/bubble
- Use `pptx.chart.data.BubbleChartData` for bubble
- Embed actual data so PowerPoint chart tools work
- Integrated into `slide_composer.py` with 3-tier fallback: native → PNG → placeholder

---

## Phase 2: Template & Brand System (CRITICAL) ✅ COMPLETE
**Status**: DONE  
**Goal**: Load corporate templates, enforce brand guidelines.

### Deliverables
- [x] `template_loader.py` - Parse .pptx templates, extract slide masters
- [x] `brand_kit.py` - Logo, colors, typography enforcement
- [x] Template layout mapping (match SlideKind to template layouts)
- [ ] 3 starter templates (Corporate, Startup, Academic) - Future work
- [x] Brand color locking (prevent drift)

### Technical Approach
- `Presentation(template_path)` for loading
- Extract `slide_layouts` and map by name pattern
- Brand kit as JSON/YAML with validation
- `TemplateSlideComposer` extends base `SlideComposer`

---

## Phase 3: Data Research Integration (CRITICAL) ✅ COMPLETE
**Status**: DONE  
**Goal**: Auto-fetch real data for charts, not placeholders.

### Deliverables
- [x] `data_researcher.py` - Web search + data extraction
- [x] Integration with OutlinePlanner for chart data
- [x] CSV/Excel data ingestion support (via manual data)
- [x] Data source attribution in chart titles
- [x] Caching layer for research results

### Technical Approach
- Perplexity/Search API for market data, trends
- Data extraction from unstructured text
- Cache TTL: 1 hour for volatile, 24h for stable
- `research_chart_data()` one-shot convenience function

---

## Phase 4: Tables & Advanced Layouts ✅ COMPLETE
**Status**: DONE  
**Goal**: Add table support and dynamic layouts.

### Deliverables
- [x] Table rendering with styles (light/medium/dark)
- [x] `table` SlideKind in schemas
- [x] `TableSpec` Pydantic model with headers/rows
- [x] Auto-table generation from data
- [ ] Grid layout system (2x2, 3x3 content grids) - Phase 6
- [ ] Masonry-style content flows - Phase 6

---

## Phase 5: Visual Assets & Icons ✅ COMPLETE
**Status**: DONE  
**Goal**: Rich visual vocabulary beyond photos.

### Deliverables
- [x] Icon library with 20+ built-in icons (Material Design based)
- [x] Icon search by semantic query
- [x] SVG to PNG conversion (cairosvg + svglib fallbacks)
- [x] Consistent icon sizing and color theming
- [x] Semantic mappings (growth → trending_up, chart, rocket)
- [ ] Font Awesome / Heroicons full integration - Future work
- [ ] Shape primitives (arrows, badges, callouts) - Phase 6

### Files Created
- `icon_library.py` - IconLibrary class with search, render functions
- `find_icon()` - One-shot icon lookup
- `render_icon_for_slide()` - Async render for slide composition

---

## Phase 6: SmartArt-Style Diagrams ✅ COMPLETE
**Status**: DONE  
**Goal**: Process flows, hierarchies, cycles.

### Deliverables
- [x] Process diagram (linear flow with arrows)
- [x] Cycle diagram (circular)
- [x] Hierarchy/tree diagram (org charts)
- [ ] Venn diagram (2-3 circles) - Future work
- [x] Pyramid/funnel visual
- [x] Timeline/gantt-style layouts

### Files Created
- `smartart_renderer.py` - SmartArtRenderer with 6 diagram types
- `render_smartart()` - One-shot convenience function

---

## Phase 7: Polish & Accessibility ✅ COMPLETE
**Status**: DONE  
**Goal**: Production-grade finish.

### Deliverables
- [x] Slide transitions framework (limited python-pptx support)
- [x] Animation framework (chart build by series)
- [x] Alt text for all images/charts
- [x] Reading order validation
- [x] Color contrast compliance checking (WCAG)
- [x] PDF export option (LibreOffice/unoconv)

### Files Created
- `polish_engine.py` - PolishEngine with accessibility validation
- `apply_polish()` - One-shot polish application
- `validate_presentation()` - Accessibility audit
- `export_to_pdf()` - PDF conversion

---

## Phase 8: Quality Validation ✅ COMPLETE
**Status**: DONE  
**Goal**: Self-correcting agent.

### Deliverables
- [x] Content consistency checker (contradictions, repetition, vague)
- [x] Narrative flow scoring (structure detection)
- [x] Design principle validation (variety, data ratio, text density)
- [x] Auto-revision suggestions for flagged issues
- [x] Confidence scoring per slide (0.0-1.0)

### Files Created
- `quality_validator.py` - QualityValidator with full scoring
- ValidationReport with narrative, content, design scores
- Revision suggestions with priority and expected improvement
- `quick_validate()` - One-shot validation

---

## Implementation Order

1. **WEEK 1**: Phase 1 (Native Charts) + Phase 2 (Templates)
2. **WEEK 2**: Phase 3 (Data Research) + Phase 4 (Tables)
3. **WEEK 3**: Phase 5 (Icons) + Phase 6 (SmartArt)
4. **WEEK 4**: Phase 7 (Polish) + Phase 8 (Validation)

## Success Metrics

- [ ] Charts editable in PowerPoint (click chart → see data)
- [ ] Templates load and render correctly
- [ ] Real data in at least 30% of charts
- [ ] Zero placeholder cards in production
- [ ] Professional design critique: 8/10+

## Files to Create/Modify

### New Files
- `ai_engine/agents/ppt/native_chart_renderer.py`
- `ai_engine/agents/ppt/template_loader.py`
- `ai_engine/agents/ppt/brand_kit.py`
- `ai_engine/agents/ppt/data_researcher.py`
- `ai_engine/agents/ppt/table_renderer.py`
- `ai_engine/agents/ppt/icon_library.py`
- `ai_engine/agents/ppt/smartart_renderer.py`
- `ai_engine/agents/ppt/quality_validator.py`

### Modified Files
- `ai_engine/agents/ppt/schemas.py` - Add table kind, smartart specs
- `ai_engine/agents/ppt/outline_planner.py` - Integrate data research
- `ai_engine/agents/ppt/slide_composer.py` - Native chart paths, templates
- `ai_engine/agents/ppt/ppt_orchestrator.py` - New renderer injection
- `ai_engine/agents/ppt/chart_renderer.py` - Keep as PNG fallback

---

**Start Date**: 2026-05-03  
**Target Completion**: 2026-05-31  
**Owner**: Cascade AI
