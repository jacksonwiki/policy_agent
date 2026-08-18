#!/bin/bash
cd "/Users/yang/wise/policy_agent/frontend"
exec npm run dev >> "/Users/yang/wise/policy_agent/logs/frontend.log" 2>&1
