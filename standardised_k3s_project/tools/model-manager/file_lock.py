"""OS file locks; Windows support is for isolated browser fixtures."""
import os
def lock_file(stream):
 if os.name=="nt":
  import msvcrt
  stream.seek(0,2)
  if stream.tell()==0:stream.write(" ");stream.flush()
  stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_LOCK,1)
 else:
  import fcntl
  fcntl.flock(stream,fcntl.LOCK_EX)
