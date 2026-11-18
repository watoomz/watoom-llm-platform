#!/usr/bin/env python3
"""Loopback-only staging access, reconnecting across pod replacement."""
import subprocess,time
while True:
 subprocess.run(['kubectl','-n','watoom-code','port-forward','service/watoom-code','14097:4096','--address','127.0.0.1'])
 time.sleep(2)
