# Pre-Deployment Checklist: Streaming + Performance Fix

**Date**: 2026-04-13  
**Status**: Ready for Production  
**Risk Level**: LOW (adding only instrumentation + flushing, no core logic changes)

## Code Review Checklist

- [x] `backend/app/api/routes/generate/stream.py` - Added heartbeat + flush points
- [x] `backend/tests/test_streaming_heartbeat.py` - Unit tests included
- [x] No breaking changes to API contracts
- [x] No changes to frontend needed
- [x] All files pass syntax validation (`python -m py_compile`)
- [x] Backward compatible (non-breaking changes only)

## Testing Checklist

- [ ] Run unit tests: `pytest backend/tests/test_streaming_heartbeat.py -v`
- [ ] Start backend service locally
- [ ] Run generation test with valid job description
- [ ] Open browser DevTools → Network tab
- [ ] Verify `/api/generate/jobs/{jobId}/stream` shows events flowing
- [ ] Verify frontend shows progress % updating every 3-5s
- [ ] Check backend logs for timing breakdown
- [ ] Verify generation completes successfully

## Deployment Checklist

- [ ] Reviewed `STREAMING_FIX_QUICK_START.md`
- [ ] Reviewed `STREAMING_FIX_DEPLOYMENT_GUIDE.md`
- [ ] All tests passing
- [ ] No merge conflicts
- [ ] Backend container builds successfully
- [ ] Staging environment deployed and tested
- [ ] Monitoring/alerting rules ready (optional but recommended)

## Production Checklist

- [ ] Deploy to production via normal process (Railway, etc.)
- [ ] Monitor backend logs for errors (first 10 minutes)
- [ ] Check that new logs appear: `agent_pipeline.documents_generated`
- [ ] Run smoke test generation in production
- [ ] Verify users see progress updates during generation
- [ ] Check performance metrics (no degradation expected)
- [ ] Set up dashboard to track timing metrics

## Rollback Plan (if needed)

```bash
# If issues arise, quick rollback:
git revert <commit-sha>
git push origin main
# Or:
git reset --hard <previous-commit>
git push -f origin main
```

## Monitoring (Recommended)

### Logs to Watch
```
agent_pipeline.documents_generated
agent_pipeline.portfolio_generated
agent_pipeline.complete
agent_pipeline.circuit_breaker_open
agent_pipeline - ERROR
```

### Metrics to Track
```
- Mean documents generation time (target: 40-60s)
- Mean portfolio generation time (target: 20-30s)
- Percentage of jobs completing successfully (target: >95%)
- Percentage of jobs hitting inactivity timeout (target: 0%)
```

### Alerts to Create
```
- elapsed_seconds > 120 for any pipeline phase
- error rate > 5% for generation pipeline
- Response time > 180s for generation endpoint
```

## Verification Steps

### Step 1: Check Syntax (Pre-deployment)
```bash
python -m py_compile backend/app/api/routes/generate/stream.py
python -m py_compile backend/tests/test_streaming_heartbeat.py
```

### Step 2: Run Unit Tests (Pre-deployment)
```bash
cd backend
pytest tests/test_streaming_heartbeat.py -v
```

### Step 3: Verify Backend Compiles
```bash
# docker build or your build process
docker build -t hirestack-backend -f backend/Dockerfile .
```

### Step 4: Quick Smoke Test (Post-deployment)
```bash
# Start generation and verify:
curl -X POST https://api.example.com/api/generate/jobs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"application_id":"test-app","requested_modules":["cv"]}'

# Check response stream
curl -X GET https://api.example.com/api/generate/jobs/JOB_ID/stream \
  -H "Authorization: Bearer $TOKEN" | head -20
```

### Step 5: Monitor Logs (Post-deployment)
```bash
# Watch for timing logs (indicates heartbeat is working)
tail -f /var/log/application.log | grep "agent_pipeline"

# Expected output:
# agent_pipeline.documents_generated elapsed_seconds=42.3 cv_ok=True cl_ok=True roadmap_ok=True
# agent_pipeline.portfolio_generated elapsed_seconds=28.1 ps_ok=True pf_ok=True
```

## Sign-Off

- [ ] Code Review Approved
- [ ] QA Testing Passed
- [ ] Product Owner Approved
- [ ] Ready for Production Deployment

---

**Deploy Date**: ___________  
**Deployed By**: ____________  
**Verification Completed**: ___________  

## Post-Deployment Notes

(Use this section to record any issues or observations during deployment)

```
[Leave blank - fill after deployment]
```
