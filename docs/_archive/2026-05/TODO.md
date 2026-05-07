# PPT Agent Feature

## Phase 1: Templates ✅ [In Progress]
- ai_engine/data/ppt_templates/sales_pitch.json
- investor_deck.json
- resume_summary.json

## Phase 2: Agents
- ai_engine/agents/ppt/ppt_orchestrator.py
- ppt_researcher.py
- ppt_outliner.py
- ppt_builder.py
- ppt_critic.py

## Phase 3: Backend API
- backend/app/api/routes/ppt.py
- /api/generate/ppt POST
- /ppt/stream SSE

## Phase 4: Frontend
- frontend/src/features/ppt/
- Form, preview, download

## Phase 5: Integration
- orchestrator.tools "generate_ppt"

**Next**: Create templates dir/files.
