#!/bin/bash

# Fetch all available tasks
curl -X GET "https://wattcoin-production-81a7.up.railway.app/tasks" \
     -H "Accept: application/json"
