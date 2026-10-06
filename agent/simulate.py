"""Simulated ESP32: posts fake readings so you can run the system with no hardware.

Usage: python simulate.py [URL] [--token DEVICE_TOKEN] [--duration SECONDS]
The token can also come from the EDGE_DEVICE_TOKEN environment variable
(needed only when the gateway has EDGE_DEVICE_TOKENS set).
"""
import argparse
import os
import random
import time

import httpx

ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
ap.add_argument("url", nargs="?", default="http://localhost:8000")
ap.add_argument("--token", default=os.getenv("EDGE_DEVICE_TOKEN"),
                help="device bearer token (default: $EDGE_DEVICE_TOKEN)")
ap.add_argument("--duration", type=float, default=0,
                help="stop after this many seconds (default: run forever)")
args = ap.parse_args()

headers = {"Authorization": f"Bearer {args.token}"} if args.token else {}
temp = 45.0
start = time.monotonic()
with httpx.Client(headers=headers) as client:
    while not args.duration or time.monotonic() - start < args.duration:
        temp += random.uniform(-2, 4)  # drifts upward so alerts eventually fire
        payload = {
            "device_id": "SIM:00:11:22",
            "temperature_c": round(temp, 1),
            "rssi": random.randint(-90, -40),
            "uptime_s": int(time.monotonic()),
            "free_heap": random.randint(15_000, 200_000),
        }
        r = client.post(f"{args.url}/readings", json=payload)
        print(payload["temperature_c"], "->", r.json())
        if r.status_code in (401, 403):
            raise SystemExit("gateway rejected the device token (use --token)")
        if temp > 95:
            temp = 45.0
        time.sleep(1)
