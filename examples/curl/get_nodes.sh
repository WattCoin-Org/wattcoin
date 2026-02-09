#!/bin/bash

# Fetch registered network nodes
curl -X GET "https://wattcoin-production-81a7.up.railway.app/nodes" \
     -H "Accept: application/json"
