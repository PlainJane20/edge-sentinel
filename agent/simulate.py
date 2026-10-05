"""Simulated ESP32: posts fake readings so you can run the system with no hardware."""
import random
import sys
import time

import httpx

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"

temp = 45.0
with httpx.Client() as client:
    while True:
        temp += random.uniform(-2, 4)  # drifts upward so alerts eventually fire
        payload = {
            "device_id": "SIM:00:11:22",
            "temperature_c": round(temp, 1),
            "rssi": random.randint(-90, -40),
            "uptime_s": int(time.monotonic()),
            "free_heap": random.randint(15_000, 200_000),
        }
        r = client.post(f"{URL}/readings", json=payload)
        print(payload["temperature_c"], "->", r.json())
        if temp > 95:
            temp = 45.0
        time.sleep(1)
