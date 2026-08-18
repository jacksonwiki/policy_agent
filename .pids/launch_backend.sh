#!/bin/bash
cd "/Users/yang/wise/policy_agent"
export POLICY_AGENT_MOCK_LLM=true
exec /Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 >> "/Users/yang/wise/policy_agent/logs/backend.log" 2>&1
