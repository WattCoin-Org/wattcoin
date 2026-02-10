## Summary

Implements enhanced health check endpoint as requested in issue #90 (Bounty Card #44).

## Changes

- **Detailed Mode**: Added `?detailed=true` query parameter support for extended system metrics
- **System Metrics**: When detailed mode is enabled, returns:
  - Memory: total, available, percent used
  - CPU: load percentage  
  - Disk: usage stats for /app/data directory
- **External Service Validation**: Detailed mode performs lightweight connectivity checks for AI API and Claude API
- **Database Connectivity**: Enhanced to verify file readability, not just existence
- **Claude API Check**: Added `claude_api` to services status checks
- **Error Handling**: Added comprehensive try/except for graceful degradation
- **Backward Compatibility**: All existing fields maintained for non-detailed requests

## API Changes

### Basic Health (unchanged)
```
GET /health
```
Returns: `status`, `version`, `uptime_seconds`, `services`, `active_nodes`, `open_tasks`, `timestamp`

### Enhanced Health (new)
```
GET /health?detailed=true
```
Returns all basic fields plus:
- `detailed: true`
- `system.memory`: Memory metrics
- `system.cpu`: CPU metrics 
- `system.disk`: Disk usage metrics
- Enhanced `services.claude_api`: Claude API key and connectivity status

## Tests

All tests in `tests/test_health_endpoint.py`:
- ✅ Health returns 200 when healthy
- ✅ Health returns 503 when critical services down
- ✅ Detailed mode returns extended metrics
- ✅ Claude API service checks work
- ✅ System metrics have correct structure
- ✅ Database connectivity is validated
- ✅ Backward compatibility maintained
- ✅ Error handling works gracefully

## Files Changed

- `bridge_web.py`: Extended health endpoint with enhanced functionality
- `requirements.txt`: Added `psutil` for system metrics
- `tests/test_health_endpoint.py`: Added comprehensive tests

## Bounty

Card #44 - WattCoin Health Check (2,000 WATT)

---

**Note**: This PR includes no new demo video (not required for backend Python bounties per bounty description). The implementation is production-ready with comprehensive tests.
