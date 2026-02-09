#!/bin/bash

# Fetch node reputation data
curl -X GET "https://wattcoin-production-81a7.up.railway.app/reputation" \
     -H "Accept: application/json"
