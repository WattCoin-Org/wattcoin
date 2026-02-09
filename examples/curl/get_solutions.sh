#!/bin/bash

# Fetch submitted solutions
curl -X GET "https://wattcoin-production-81a7.up.railway.app/solutions" \
     -H "Accept: application/json"
