import json
import os
import sys
import time

GAUGE_FILE = "gauge_readings.json"
INTENT_FILE = "intent.json"
VOTING_FILE = "voting_records.json"
DO_FILE = "do_action.json"
MASTER_LOG_FILE = "master_flight_log.json"

MAX_PITCH_UP = 35.0
MAX_PITCH_DOWN = -35.0
PITCH_STEP_LIMIT = 4.0


def read_json_safe(filepath, default=None):
    if not os.path.exists(filepath):
        return default
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except Exception:
        return default


def write_json_atomic(filepath, data):
    temp_path = f"{filepath}.tmp"
    with open(temp_path, "w") as f:
        json.dump(data, f, indent=4)
    os.replace(temp_path, filepath)


def run_computer(comp_id):
    comp_name = f"Computer {comp_id}"
    comp_file = f"{comp_name}.json"

    # Internal target state for gradual pitch transitions
    target_aoa = 0.0

    print(f"=== {comp_name} ONLINE ===")

    last_processed_cycle = -1

    while True:
        gauge_data = read_json_safe(GAUGE_FILE)
        if not gauge_data:
            time.sleep(0.1)
            continue

        cycle = gauge_data.get("clock_cycle", 0)
        if cycle == last_processed_cycle:
            time.sleep(0.1)
            continue

        last_processed_cycle = cycle

        # -------------------------------------------------------------
        # 1. READ INTENT AND SENSOR TELEMETRY
        # -------------------------------------------------------------
        intent_data = read_json_safe(INTENT_FILE, {})
        pilot_intent = intent_data.get("intent", "CRUISE")
        pitch_delta = intent_data.get("pitch_delta", 0.0)

        aoa_sensors = gauge_data.get("aoa_sensors", {})
        sensor_vals = list(aoa_sensors.values())
        current_aoa = (
            sum(sensor_vals) / len(sensor_vals) if sensor_vals else 0.0
        )

        # Calculate target pitch
        if pilot_intent == "MANUAL_PITCH":
            raw_target = current_aoa + pitch_delta
            target_aoa = max(MAX_PITCH_DOWN, min(MAX_PITCH_UP, raw_target))
        elif pilot_intent == "CLIMB":
            target_aoa = min(MAX_PITCH_UP, current_aoa + 10.0)
        elif pilot_intent == "DESCEND":
            target_aoa = max(MAX_PITCH_DOWN, current_aoa - 10.0)
        else:
            # Autopilot default: Decay 25% back toward 0°
            target_aoa = current_aoa * 0.75

        # Apply gradual step constraint (Max 4° movement per clock cycle)
        delta = target_aoa - current_aoa
        if abs(delta) > PITCH_STEP_LIMIT:
            step = PITCH_STEP_LIMIT if delta > 0 else -PITCH_STEP_LIMIT
            proposed_aoa = current_aoa + step
        else:
            proposed_aoa = target_aoa

        # Write proposed calculation to own computer file (e.g. Computer 1.json)
        my_output = {
            "computer": comp_name,
            "clock_cycle": cycle,
            "proposed_aoa": round(proposed_aoa, 2),
            "target_aoa": round(target_aoa, 2),
        }
        write_json_atomic(comp_file, my_output)

        # Allow time for peer nodes to write their outputs
        time.sleep(0.15)

        # -------------------------------------------------------------
        # 2. PEER EVALUATION & VOTING
        # -------------------------------------------------------------
        peer_outputs = {}
        for i in range(1, 4):
            p_data = read_json_safe(f"Computer {i}.json")
            if p_data and p_data.get("clock_cycle") == cycle:
                peer_outputs[f"Computer {i}"] = p_data.get("proposed_aoa", 0.0)

        # Determine if peers deviate > 5% relative to local calculation
        voted_out_target = "None"
        if len(peer_outputs) > 1:
            my_val = peer_outputs.get(comp_name, proposed_aoa)
            for p_name, p_val in peer_outputs.items():
                if p_name == comp_name:
                    continue
                err = abs(p_val - my_val) / (abs(my_val) + 1e-5)
                if err > 0.05:
                    voted_out_target = p_name
                    break

        # Append ballot to shared voting record file
        vote_entry = {
            "clock_cycle": cycle,
            "voter": comp_name,
            "voted_out": voted_out_target,
        }

        voting_records = read_json_safe(VOTING_FILE, [])
        if not isinstance(voting_records, list):
            voting_records = []
        voting_records.append(vote_entry)
        write_json_atomic(VOTING_FILE, voting_records)

        # Allow time for all votes to arrive
        time.sleep(0.15)

        # -------------------------------------------------------------
        # 3. MASTER INITIATIVE & DO FILE EXECUTION
        # -------------------------------------------------------------
        current_votes = read_json_safe(VOTING_FILE, [])
        if not isinstance(current_votes, list):
            current_votes = []
        cycle_votes = [
            v for v in current_votes if v.get("clock_cycle") == cycle
        ]

        vote_counts = {}
        for v in cycle_votes:
            target = v.get("voted_out")
            if target and target != "None":
                vote_counts[target] = vote_counts.get(target, 0) + 1

        kicked_computer = None
        if vote_counts:
            highest = max(vote_counts.values())
            if highest >= 2:  # Majority consensus
                kicked_computer = max(vote_counts, key=vote_counts.get)

        # Determine active lead computer (Default: Computer 1 -> 2 -> 3)
        active_leader = "Computer 1"
        if kicked_computer == "Computer 1":
            active_leader = "Computer 2"
            if kicked_computer == "Computer 2":
                active_leader = "Computer 3"

        # If THIS process is the active leader, write final DO action and log
        if comp_name == active_leader:
            valid_vals = []
            for name, val in peer_outputs.items():
                if name != kicked_computer:
                    valid_vals.append(val)

            sorted_vals = sorted(valid_vals)
            n = len(sorted_vals)
            if n > 0:
                final_aoa = (
                    sorted_vals[n // 2]
                    if n % 2 == 1
                    else (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2.0
                )
            else:
                final_aoa = proposed_aoa

            do_command = {
                "clock_cycle": cycle,
                "leader": comp_name,
                "kicked_computer": kicked_computer,
                "final_aoa_action": round(final_aoa, 2),
                "timestamp": time.time(),
            }
            write_json_atomic(DO_FILE, do_command)

            # Record voting output to master log file
            master_log = read_json_safe(MASTER_LOG_FILE, [])
            if not isinstance(master_log, list):
                master_log = []
            master_log.append(
                {
                    "clock_cycle": cycle,
                    "leader": comp_name,
                    "kicked": kicked_computer,
                    "consensus_aoa": round(final_aoa, 2),
                    "votes": cycle_votes,
                }
            )
            write_json_atomic(MASTER_LOG_FILE, master_log)

            # Clear voting file for next cycle
            write_json_atomic(VOTING_FILE, [])


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python computer.py <1|2|3>")
        sys.exit(1)

    comp_number = sys.argv[1]
    run_computer(comp_number)
