import pathlib,json,subprocess,time
p=pathlib.Path('/data/ai/helper-scripts/watoom-blender-package');m=json.loads((p/'implementation/latest.json').read_text());r=pathlib.Path(m['host_root']);fixture=r/'rollback-fixture';(fixture/'reports').mkdir(parents=True,exist_ok=True)
audit=sorted((p/'evidence').glob('audit-*/report.json'))[-1];cmd=['python3',str(p/'scripts/fix-canary.py'),'--root',str(fixture),'--audit-report',str(audit)]
failure=subprocess.run(cmd+['--test-failure'],capture_output=True,text=True,timeout=15);assert failure.returncode and not (fixture/'opencode.json').exists()
time.sleep(1)
install=subprocess.run(cmd,capture_output=True,text=True,timeout=15);assert install.returncode==0
snapshot=next((fixture/'reports').glob('canary-snapshot-*/snapshot.json')).parent
idempotent=subprocess.run(cmd,capture_output=True,text=True,timeout=15);assert idempotent.returncode==0 and 'idempotent' in idempotent.stdout
rollback=subprocess.run(cmd+['--rollback','--snapshot',str(snapshot),'--i-approve'],capture_output=True,text=True,timeout=15);assert rollback.returncode==0 and not (fixture/'opencode.json').exists()
(r/'reports/rollback-test.json').write_text(json.dumps({'status':'PASS','automatic_failure_restore':'PASS','install':'PASS','idempotence':'PASS','manual_rollback':'PASS','fixture':str(fixture),'snapshot':str(snapshot),'logs':{'injected_failure':failure.stderr[-1800:],'install':install.stdout,'rollback':rollback.stdout},'scope':'disposable new canary configuration; no production modifications'},indent=2));print('PASS injected failure, install, idempotence, rollback')
