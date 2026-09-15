# Distributed Flight Control Voting Simulation

A software simulation of a fault-tolerant flight control voting system. Three independent "computer" processes each propose an angle-of-attack (AoA) command every clock cycle, cross-check each other's outputs, vote out any peer that deviates too far, and elect a leader to issue the final consolidated command.

## Architecture

```
data_generate.py  -->  gauge_readings.json  -->  computer.py (x3)  -->  Computer N.json
                                                        |
                                                        v
                                              voting_records.json
                                                        |
                                                        v
                                          (leader only) do_action.json
                                                        |
                                                        v
                                              master_flight_log.json

intent.py / Master.py  -->  intent.json  -->  computer.py (reads pilot intent)
```

Each cycle, every `computer.py` instance:

1. **Reads** the latest sensor frame (`gauge_readings.json`) and pilot intent (`intent.json`).
2. **Proposes** a target AoA (bounded to ±35°, stepped at ≤4°/cycle) and writes it to its own file (`Computer N.json`).
3. **Cross-checks peers**: after a short delay to let peers write, it reads all three `Computer N.json` files and flags any peer whose value differs from its own by more than 5% as a candidate to "vote out." Its ballot is appended to `voting_records.json`.
4. **Consolidates**: after another delay, whichever computer is the current "active leader" tallies that cycle's votes. If a computer gets 2+ votes against it, it's excluded. The leader takes the median of the remaining valid values as the final command, writes it to `do_action.json`, and appends a record to `master_flight_log.json`.

This mirrors real fly-by-wire redundancy concepts (cross-channel comparison, majority voting, median/outlier-rejecting consolidation) using three OS processes and shared JSON files standing in for shared memory slots.

## Files

| File | Role |
|---|---|
| `Master.py` | Launches all processes, clears old state on startup, and is the pilot's command console |
| `data_generate.py` | Simulated sensor generator — produces noisy AoA readings and occasionally injects a wild single-sensor fault |
| `computer.py` | The voting "flight control computer" — run 3x as `computer.py 1/2/3` |
| `intent.py` | Standalone pilot input tool (alternative to typing directly into `Master.py`) |
| `gauge_readings.json` | Latest sensor frame from the generator |
| `intent.json` | Latest pilot command (CRUISE / CLIMB / DESCEND / MANUAL_PITCH) |
| `Computer 1/2/3.json` | Each computer's own latest proposed AoA |
| `voting_records.json` | Ballots cast each cycle; cleared after the leader tallies them |
| `do_action.json` | The leader's final consolidated command for the current cycle |
| `master_flight_log.json` | Full historical log of sensor frames and voting outcomes |

## Running it

```
python Master.py
```

This starts the sensor generator and all three computers as background processes, then drops you into a pilot prompt:

- `+6`, `-9`, `15`, `-20` — send a manual pitch adjustment (degrees)
- `c` / `cruise` — reset to autopilot cruise (auto-decays 25% back toward 0° each cycle)
- `e` / `exit` — shut down all background nodes (see **Known issues** below)

You can also run `python intent.py` in a separate terminal as an alternative pilot input channel.

## Known issues

- **`e` / `exit` does not always kill the background processes cleanly.** `Master.py` calls `kill_process_group()` on each launched process, but depending on your OS/terminal (especially inside an IDE console rather than a real terminal), the `computer.py` and `data_generate.py` processes can survive the exit and keep running and writing to the JSON files in the background. After typing `e`, check your process list — if `computer.py`/`data_generate.py` are still alive, force-kill them manually:
  - **Windows**: `taskkill /F /IM python.exe` (or end the individual `python.exe` tasks in Task Manager)
  - **macOS/Linux**: `pkill -f computer.py` and `pkill -f data_generate.py` (or `pkill -9 -f Master.py` to take everything down at once)

  Do this once after every `e`/`exit` until you've confirmed no stray processes remain — otherwise a new run of `Master.py` will race against zombie processes still writing to the same JSON files.

- **Leader failover logic is a nested `if`, not `elif`.** In `computer.py`, the block that picks `active_leader` when a computer is kicked can never advance past Computer 2 — the inner check `if kicked_computer == "Computer 2"` is nested inside `if kicked_computer == "Computer 1"`, so it can only run when `kicked_computer` is somehow both at once, which never happens. In practice this means if Computer 2 (not Computer 1) is voted out, leadership never fails over to Computer 3. Worth fixing to a proper `elif` chain if you want correct 3-way failover.
