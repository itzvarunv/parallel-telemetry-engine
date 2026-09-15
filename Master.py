import json
import os
import signal
import subprocess
import sys
import time

PYTHON_EXE = sys.executable
INTENT_FILE = "intent.json"

# List of files to clean ONLY on startup
STATE_FILES = [
    "gauge_readings.json",
    "master_flight_log.json",
    "voting_records.json",
    "do_action.json",
    "Computer 1.json",
    "Computer 2.json",
    "Computer 3.json",
    "intent.json",
    "intent.json.tmp",
]

PROCESS_CONFIGS = [
    {"name": "Sensor Generator", "cmd": [PYTHON_EXE, "data_generate.py"]},
    {"name": "Computer 1", "cmd": [PYTHON_EXE, "computer.py", "1"]},
    {"name": "Computer 2", "cmd": [PYTHON_EXE, "computer.py", "2"]},
    {"name": "Computer 3", "cmd": [PYTHON_EXE, "computer.py", "3"]},
]


def clear_state_files():
    """Removes temporary and log JSON files."""
    for filename in STATE_FILES:
        if os.path.exists(filename):
            try:
                os.remove(filename)
            except Exception:
                pass


def update_intent(intent_type, pitch_delta=0.0):
    """Writes pilot commands directly to intent.json."""
    data = {
        "intent": intent_type,
        "pitch_delta": float(pitch_delta),
        "timestamp": time.time(),
    }
    temp_file = f"{INTENT_FILE}.tmp"
    with open(temp_file, "w") as f:
        json.dump(data, f, indent=4)
    os.replace(temp_file, INTENT_FILE)


def kill_process_group(proc):
    """Guarantees process death even inside IDLE or restricted execution environments."""
    try:
        if proc.poll() is None:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except Exception:
                    pass

            # Direct PID fallback
            try:
                proc.kill()
                proc.wait(timeout=0.5)
            except Exception:
                pass
    except Exception:
        pass


def main():
    print("==================================================")
    print("   LAUNCHING DISTRIBUTED FLIGHT CONTROL SYSTEM   ")
    print("==================================================")

    # 1. Purge old session files before starting fresh
    print("[MASTER] Cleaning old workspace JSON files...")
    clear_state_files()
    update_intent("CRUISE", 0.0)

    running_processes = []

    # 2. Launch processes with process group isolation
    for config in PROCESS_CONFIGS:
        print(f"[MASTER] Starting {config['name']}...")
        kwargs = {}
        if os.name != "nt":
            kwargs["preexec_fn"] = os.setsid  # Create process group on Mac/Linux

        p = subprocess.Popen(config["cmd"], **kwargs)
        running_processes.append({"name": config["name"], "process": p})
        time.sleep(0.2)

    print("\n[MASTER] All system nodes running in parallel!")
    print("--------------------------------------------------")
    print("COMMANDS:")
    print("  +6, -9, 15, -20 : Send pitch adjustment (+/- deg)")
    print("  c or cruise     : Reset pitch to 0° Cruise")
    print("  e or exit       : Shut down all background nodes\n")

    try:
        while True:
            cmd = (
                input("Pilot Command (+/- Pitch or 'e' to exit) > ")
                .strip()
                .lower()
            )

            if not cmd:
                continue

            if cmd in ["e", "exit"]:
                print(
                    "\n[MASTER] Exit signal received. Hard-killing all nodes..."
                )
                break
            elif cmd in ["c", "cruise"]:
                update_intent("CRUISE", 0.0)
                print("[MASTER -> INTENT] Set to CRUISE (0°)")
            else:
                try:
                    val = float(cmd)
                    update_intent("MANUAL_PITCH", val)
                    print(f"[MASTER -> INTENT] Sent Pitch Delta: {val:+.1f}°")
                except ValueError:
                    print(
                        "[MASTER] Invalid command! Type a number (+6, -9), 'c', or 'e'."
                    )

    except KeyboardInterrupt:
        print("\n[MASTER] Interrupted by user. Cleaning up...")

    # 3. Force kill all background processes
    print("--------------------------------------------------")
    for item in running_processes:
        proc = item["process"]
        name = item["name"]
        print(f"[MASTER] Force-killing {name} (PID: {proc.pid})...")
        kill_process_group(proc)

    # Note: clear_state_files() is omitted here so your computer logs stay preserved on disk.
    print(
        "[MASTER] All processes stopped. Session JSON files preserved for inspection!"
    )


if __name__ == "__main__":
    main()
