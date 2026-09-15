import json
import os
import time

INTENT_FILE = "intent.json"


def send_target_pitch(pitch_delta):
    """Writes numerical pitch adjustment (+6, -9, etc.) to intent.json."""
    data = {
        "intent": "MANUAL_PITCH",
        "pitch_delta": float(pitch_delta),
        "timestamp": time.time(),
    }
    with open(INTENT_FILE, "w") as f:
        json.dump(data, f, indent=4)


def main():
    print("=== PILOT CONTROL INTERFACE ===")
    print("Enter numerical pitch adjustments (e.g., +6, -9, 15, -20).")
    print("Type 'c' or 'cruise' to reset to 0° Cruise.\n")

    while True:
        try:
            cmd = input("Pitch Input > ").strip().lower()

            if cmd in ["c", "cruise"]:
                send_target_pitch(0.0)
                print("[PILOT] Set intent to CRUISE (0°)")
            else:
                val = float(cmd)
                send_target_pitch(val)
                print(f"[PILOT] Sent pitch command: {val:+.1f}°")

        except ValueError:
            print("Invalid input! Please enter a number like +6 or -9.")
        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    main()
