## ToDo:

- ✅ Open PR with latest changes for codebase and merge correctly
- ✅ Finish orchestrator script
- Run tests
- Analysis, and more analysis
- WRITE text about measures

---

- Write everything else

---

## Setup

- `pidstat` for CPU/Memory usage
- `sar` for network usage
- `time` for tracking the process directly
- Additionally `cpufreqstat`, `ntp` is used
- Measurement script to automate tests
    - Config file for one runthrough
    - Scripts for running processes with parallel monitoring
    - Script for server and client measure
    - Script for orchestration (uploads scripts, runs server and client scripts remotely, stops processes, gets resulting data and creates summary of measures)
    - Comparison script for unicast and multicast that parses raw data and plots graphs

## Tests

### Multicast settings

- rate limiting 24000
- 5 iterations per runthrough, averaged
- 5 minutes each (or until finished)

### Unicast settings

- 5 iterations per runthrough, averaged
- 5 minutes each (or until finished)

### Measures for each Unicast and Multicast

- 3 clients (3 x 1 client)
- 6 clients (3 x 2 clients)
- 12 clients (3 x 4 clients)
- 24 clients (3 x 8 clients)
- 36 clients (3 x 12 clients)

