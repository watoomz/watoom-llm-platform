import importlib.util,pathlib,subprocess,sys,tempfile,time,unittest
spec=importlib.util.spec_from_file_location("bounded_process",pathlib.Path(__file__).resolve().parents[1]/"bounded_process.py")
bounded=importlib.util.module_from_spec(spec);spec.loader.exec_module(bounded)
class ProcessCancellation(unittest.TestCase):
    def test_timeout_terminates_descendant_as_well_as_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            pidfile=pathlib.Path(directory)/"child.pid"
            code="import subprocess,sys,pathlib,time;p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);pathlib.Path(sys.argv[1]).write_text(str(p.pid));time.sleep(60)"
            with self.assertRaises(subprocess.TimeoutExpired):
                bounded.run([sys.executable,"-c",code,str(pidfile)],timeout=1,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            child=int(pidfile.read_text())
            status=pathlib.Path("/proc")/str(child)/"stat"
            deadline=time.monotonic()+2
            while True:
                try:state=status.read_text().split()[2]
                except (FileNotFoundError,ProcessLookupError):state="X"
                if state in ("Z","X") or time.monotonic()>=deadline:break
                time.sleep(0.01)
            self.assertIn(state,("Z","X"),"Descendant survived timeout")
if __name__=="__main__":unittest.main()
