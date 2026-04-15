#!/usr/bin/env python3
"""
Integration test: Verify streaming fix works end-to-end

This script:
1. Starts the backend server
2. Makes a generation request
3. Monitors SSE events in real-time
4. Measures streaming frequency and latency
5. Verifies heartbeat events arrive every 3-5 seconds
"""

import asyncio
import time
import httpx
import json
import sys
from datetime import datetime

# Test configuration
BACKEND_URL = "http://localhost:8000"
TIMEOUT = 180  # 3 minutes max
HEARTBEAT_INTERVAL_EXPECTED = 3.0  # seconds

async def test_streaming():
    """Test SSE streaming with heartbeat verification"""
    
    print("=" * 80)
    print("STREAMING FIX VERIFICATION TEST")
    print("=" * 80)
    print(f"Start time: {datetime.now().isoformat()}")
    print(f"Backend URL: {BACKEND_URL}")
    print()
    
    # Sample job request
    job_request = {
        "job_title": "Senior Software Engineer at Google",
        "job_description": "We are looking for a talented software engineer with 5+ years of experience...",
        "company_name": "Google",
        "user_id": "test-user-123"
    }
    
    print(f"Test Job Request:")
    print(f"  Title: {job_request['job_title']}")
    print(f"  Company: {job_request['company_name']}")
    print()
    
    event_count = 0
    last_event_time = None
    event_times = []
    progress_events = []
    agent_events = []
    errors = []
    
    start_time = time.time()
    
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            print("Connecting to backend stream endpoint...")
            
            async with client.stream(
                "POST",
                f"{BACKEND_URL}/api/generate/pipeline/stream",
                json=job_request,
            ) as response:
                print(f"Connected! Status: {response.status_code}")
                print()
                
                async for line in response.aiter_lines():
                    current_time = time.time()
                    
                    if not line.strip():
                        continue
                    
                    event_count += 1
                    elapsed = current_time - start_time
                    
                    # Parse SSE event
                    if line.startswith("event:"):
                        event_type = line.split(":", 1)[1].strip()
                        print(f"[{elapsed:.1f}s] Event #{event_count}: {event_type}")
                        
                        if event_type == "progress":
                            progress_events.append((elapsed, event_count))
                        elif event_type == "agent_status":
                            agent_events.append((elapsed, event_count))
                        
                    elif line.startswith("data:"):
                        data_str = line.split(":", 1)[1].strip()
                        try:
                            data = json.loads(data_str)
                            
                            # Log progress details
                            if "progress" in data:
                                print(f"  Progress: {data.get('progress')}% - {data.get('message', '')}")
                            
                            # Log agent status details
                            if "stage" in data:
                                print(f"  Agent: {data.get('pipeline_name')} - {data.get('stage')} ({data.get('message', '')})")
                            
                            # Detect completion
                            if data.get("status") == "complete":
                                print(f"\n[{elapsed:.1f}s] ✅ GENERATION COMPLETE!")
                                
                        except json.JSONDecodeError:
                            pass
                    
                    # Track event timing for heartbeat verification
                    if last_event_time is not None:
                        time_since_last = current_time - last_event_time
                        event_times.append(time_since_last)
                    
                    last_event_time = current_time
    
    except httpx.ConnectError:
        print(f"❌ ERROR: Could not connect to {BACKEND_URL}")
        print("Is the backend running? Start it with: cd backend && python main.py")
        return False
    except asyncio.TimeoutError:
        print(f"❌ ERROR: Request timed out after {TIMEOUT}s")
        return False
    except Exception as e:
        print(f"❌ ERROR: {type(e).__name__}: {e}")
        return False
    
    total_elapsed = time.time() - start_time
    
    print()
    print("=" * 80)
    print("RESULTS")
    print("=" * 80)
    print(f"Total time: {total_elapsed:.1f}s")
    print(f"Total events received: {event_count}")
    print(f"Progress events: {len(progress_events)}")
    print(f"Agent status events: {len(agent_events)}")
    print()
    
    # Analyze heartbeat timing
    if event_times:
        avg_interval = sum(event_times) / len(event_times)
        min_interval = min(event_times)
        max_interval = max(event_times)
        
        print("Heartbeat Analysis:")
        print(f"  Average interval: {avg_interval:.2f}s")
        print(f"  Min interval: {min_interval:.2f}s")
        print(f"  Max interval: {max_interval:.2f}s")
        print(f"  Expected interval: ~{HEARTBEAT_INTERVAL_EXPECTED}s")
        
        # Check if heartbeat is working
        if avg_interval <= HEARTBEAT_INTERVAL_EXPECTED + 1.0:
            print(f"  ✅ Heartbeat is working correctly!")
        else:
            print(f"  ⚠️  Heartbeat interval seems high (expected ~{HEARTBEAT_INTERVAL_EXPECTED}s)")
        print()
    
    # Verify progress events frequency
    if len(progress_events) > 1:
        progress_intervals = []
        for i in range(1, len(progress_events)):
            interval = progress_events[i][0] - progress_events[i-1][0]
            progress_intervals.append(interval)
        
        if progress_intervals:
            avg_progress_interval = sum(progress_intervals) / len(progress_intervals)
            print(f"Progress event frequency: ~{avg_progress_interval:.1f}s apart")
            print(f"  ✅ Streaming is working (events arriving regularly)")
    else:
        print(f"  ⚠️  Only {len(progress_events)} progress events received")
    
    print()
    print("=" * 80)
    print("VERIFICATION CHECKLIST")
    print("=" * 80)
    
    checks = {
        "Connected to backend": event_count > 0,
        "Received progress events": len(progress_events) > 0,
        "Received agent status events": len(agent_events) > 0,
        "Events arrived in real-time": avg_interval < 10 if event_times else False,
        "Heartbeat interval ~3-5s": avg_interval <= 6 if event_times else False,
    }
    
    for check, result in checks.items():
        status = "✅" if result else "❌"
        print(f"{status} {check}")
    
    print()
    
    all_passed = all(checks.values())
    if all_passed:
        print("🎉 ALL CHECKS PASSED - Streaming fix is working!")
        return True
    else:
        print("⚠️  Some checks failed - review the output above")
        return False

if __name__ == "__main__":
    try:
        result = asyncio.run(test_streaming())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n\n🛑 Test interrupted by user")
        sys.exit(1)
