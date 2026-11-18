"""Prepare only bounded Godot worker writable mounts; never remove caches."""
import pathlib,os
def prepare_worker_directories(project):
 project=pathlib.Path(project)
 if project.is_symlink() or project.resolve()!=project:raise ValueError('Canonical project required')
 created=[]
 for name in ['.godot','.opencode']:
  path=project/name
  try:path.mkdir(mode=0o775);created.append(name)
  except FileExistsError:pass
  if path.is_symlink() or not path.is_dir() or path.resolve()!=path:raise ValueError('Unsafe worker mount: '+name)
  if name in created:os.chown(path,1009,1009)
 return created
