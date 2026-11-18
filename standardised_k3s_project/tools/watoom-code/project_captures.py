#!/usr/bin/env python3
"""Expose project-local captures in the common viewer directory without duplicating files."""
import argparse,json,os,pathlib
PROJECTS=pathlib.Path("/data/ai/projects")
CAPTURES=pathlib.Path("/data/ai/captures")
def register(project,projects=PROJECTS,captures=CAPTURES):
 project=pathlib.Path(project).resolve(strict=True);projects=pathlib.Path(projects).resolve(strict=True)
 if project==projects or not project.is_relative_to(projects):raise ValueError("A project inside the canonical project root is required")
 relative=project.relative_to(projects)
 source=project/".opencode/captures"
 if source.is_symlink() or not source.resolve().is_relative_to(project):raise ValueError("Capture source must remain inside its project")
 source.mkdir(parents=True,exist_ok=True)
 captures=pathlib.Path(captures).resolve(strict=True);target=captures/relative
 if not target.parent.resolve().is_relative_to(captures):raise ValueError("Capture index parent escapes shared root")
 target.parent.mkdir(parents=True,exist_ok=True)
 if target.is_symlink():
  if target.resolve()!=source.resolve():raise ValueError("Existing capture index points to another project")
 elif target.exists():raise ValueError("Existing capture directory will not be overwritten")
 else:target.symlink_to(source,target_is_directory=True)
 return {"project":str(project),"write_captures_to":str(source),"view_captures_at":str(target)}
if __name__=="__main__":
 ap=argparse.ArgumentParser();ap.add_argument("--project",required=True,type=pathlib.Path);a=ap.parse_args()
 print(json.dumps(register(a.project)))
