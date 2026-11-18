"""ExecStopPost hook for watoom-moss-image.service: if the service died while it owned the GPU, ask the controller to
recover (restore the LLM). The controller itself refuses unless the recorded owner process is really gone, so this
never takes over from a live session; the hook only decides whether there is anything to recover.

Exit status is 0 even when recovery is rejected (a failing ExecStopPost would mark the unit failed and hide the real
cause); the outcome is printed to the journal and the controller state stays authoritative for the operator."""
import pathlib
import sys

JOB = "moss-image"
HERE = pathlib.Path(__file__).resolve().parent


def recover(client, log=print):
    """Return 'none' (not our ownership), 'recovered' or 'rejected'."""
    try:
        state = client.call("status")
    except Exception as exc:
        log("moss-image recover: controller status unavailable: %s" % exc)
        return "rejected"
    if state.get("owner") != JOB:
        log("moss-image recover: controller owner is %r; nothing to recover" % (state.get("owner"),))
        return "none"
    try:
        client.call("recover", job=JOB, generation=state["generation"])
    except Exception as exc:
        log("moss-image recover: controller refused or failed (operator must reconcile): %s" % exc)
        return "rejected"
    log("moss-image recover: LLM restore requested for generation %s" % state["generation"])
    return "recovered"


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--controller-socket", default="/data/ai/helper-scripts/state/gpu-controller-private/worker.sock")
    ap.add_argument("--tools-dir", default=str(HERE.parent))
    args = ap.parse_args(argv)
    sys.path.insert(0, str(pathlib.Path(args.tools_dir) / "llm" / "watoom-gpu-controller"))
    from client import GPUClient
    recover(GPUClient(args.controller_socket, timeout=1500))
    return 0


if __name__ == "__main__":
    sys.exit(main())
