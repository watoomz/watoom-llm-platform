"""Bounded Linux operator commands with process-group cancellation."""
import os,signal,subprocess
def run(args, *, timeout=60, input=None, capture_output=False, **kwargs):
    if capture_output:
        kwargs["stdout"]=subprocess.PIPE
        kwargs["stderr"]=subprocess.PIPE
    if input is not None:kwargs["stdin"]=subprocess.PIPE
    process=subprocess.Popen(args,start_new_session=True,**kwargs)
    try:
        stdout,stderr=process.communicate(input=input,timeout=timeout)
        return subprocess.CompletedProcess(args,process.returncode,stdout,stderr)
    except BaseException:
        try:os.killpg(process.pid,signal.SIGTERM)
        except ProcessLookupError:pass
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        try:os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        process.wait()
        raise
    finally:
        for stream in (process.stdin,process.stdout,process.stderr):
            if stream is not None:stream.close()
