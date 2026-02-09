#!/bin/bash

# Fetch network statistics
curl -X GET "https://wattcoin-production-81a7.up.railway.app/stats" \
     -H "Accept: application/json"
