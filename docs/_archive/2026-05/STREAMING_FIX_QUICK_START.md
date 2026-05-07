# Streaming & Performance Fix - QUICK START

## Problem
- ❌ Generation takes 120+ seconds (looks frozen)
- ❌ No real-time progress updates (user thinks app crashed)
- ❌ Multiple long phases with no feedback

## Solution Applied 
- ✅ Added heartbeat progress every 3-5 seconds during long phases
- ✅ Added explicit flush points after critical events
- ✅ Added timing instrumentation to identify bottlenecks

## Files Changed
- `backend/app/api/routes/generate/stream.py` (+154 lines)
  - New `_run_with_heartbeat()` helper
  - Wrapped CV generation with heartbeat
  - Wrapped portfolio generation with heartbeat
  - Added flush points + timing logs

- `backend/tests/test_streaming_heartbeat.py` (NEW)
  - Unit tests for heartbeat function
  - Tests streaming behavior

- `STREAMING_FIX_DEPLOYMENT_GUIDE.md` (NEW)
  - Full deployment & testing guide

## What Happens Now

### During Generation
**BEFORE**:
```
[User waits 30 seconds for CV generation... nothing happens... UI looks frozen]
[Finally CV finishes, portfolio starts... another 20 seconds of nothing]
[Total: 120+ seconds with no feedback]
```

**AFTER**:
```
[User sees: "Running cv_generation… (5s elapsed)" - progress updated]
[3-5 seconds pass]
[User sees: "Running cv_generation… (10s elapsed)" - progress updated]
[User feels UI is responsive, generation is working]
[Total: Still 120s for actual AI work, but FEELS responsive]
```

### In Backend Logs
**AFTER**:
```
agent_pipeline.documents_generated elapsed_seconds=42.3 cv_ok=True cl_ok=True roadmap_ok=True
agent_pipeline.portfolio_generated elapsed_seconds=28.1 ps_ok=True pf_ok=True
```

Now you can identify slow phases and optimize them.

## Quick Test
1. Start generation
2. Open DevTools (F12) → Network tab
3. Find `/api/generate/jobs/{jobId}/stream`
4. Watch Response tab - should see events flowing in real-time:
   ```
   event: progress
   data: {"phase":"documents","progress":50,"message":"Running cv_generation… (5s elapsed)"}

   event: progress
   data: {"phase":"documents","progress":55,"message":"Running cv_generation… (10s elapsed)"}
   ```

## Deployment
```bash
# Review changes
git diff backend/app/api/routes/generate/stream.py

# Commit
git add backend/app/api/routes/generate/stream.py backend/tests/test_streaming_heartbeat.py STREAMING_FIX_DEPLOYMENT_GUIDE.md
git commit -m "feat: add streaming heartbeat + flush for generation responsiveness

- Added _run_with_heartbeat() helper to emit progress every 3-5s
- Wrapped CV, CL, PS, portfolio generation with heartbeat
- Added explicit flush points after critical events
- Added per-phase timing instrumentation logs
- No changes to frontend needed (already compatible)

Benefits:
- Users see progress updates every 3-5s (not frozen)
- Backend logs show per-phase timing for optimization
- Prevents inactivity timeout (frontend 120s default)
- Streaming still same total time (~100-150s) but FEELS responsive"

# Push to production
git push
```

## Expected Impact
- **User Experience**: Generation still takes ~100-150s, but UI updates every 3-5s → feels 10x more responsive
- **Developer Experience**: Backend logs now show exact phase timings → can identify + fix slow phases
- **No Breaking Changes**: Frontend is already compatible, no redeployment needed

## Troubleshooting
See `STREAMING_FIX_DEPLOYMENT_GUIDE.md` for full troubleshooting and testing procedures.

---

**Status**: Ready for production deployment  
**Risk Level**: Low (only adds logging + flush points, no core logic changes)  
**Testing**: Included unit tests in `backend/tests/test_streaming_heartbeat.py`
