#!/bin/bash

# Fetch active bounties
curl -X GET "https://wattcoin-production-81a7.up.railway.app/bounties" \
     -H "Accept: application/json"
