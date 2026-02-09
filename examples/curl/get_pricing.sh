#!/bin/bash

# Fetch current energy pricing information
curl -X GET "https://wattcoin-production-81a7.up.railway.app/pricing" \
     -H "Accept: application/json"
