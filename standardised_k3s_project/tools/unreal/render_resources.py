"""Measured resource selection for one GPU-fenced editor attempt."""
def profile(available,logical):
    gib=1024**3
    maximum=min(24*gib,((available-2*gib)//gib)*gib)
    if maximum<12*gib:
        raise ValueError("Insufficient headroom after capacity drain")
    workers=6 if maximum>=24*gib else 4 if maximum>=16*gib else 3
    cpu=max(1,min(10,logical-2))
    return {"parallel_actions":(maximum+3*gib-1)//(3*gib),"memory_max_bytes":maximum,
        "memory_high_bytes":maximum-2*gib,"cpu_quota":str(cpu*100000)+" 100000",
        "maximum_build_seconds":3600,"shader_workers":workers,"host_reserve_bytes":2*gib,
        "available_before":available,"status":"MEASURED_PREFLIGHT_PASS"}
