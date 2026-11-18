#!/usr/bin/env python3
"""Prepare a disposable Unreal acceptance project; never compile or run the engine."""
import argparse, hashlib, json, os, pathlib

ap = argparse.ArgumentParser()
ap.add_argument("--evidence", type=pathlib.Path, required=True)
a = ap.parse_args()
plan = json.loads((a.evidence / "build-plan.json").read_text())
build = pathlib.Path(plan["isolated_root"]).resolve()
assert build.is_relative_to(pathlib.Path("/data/ai/builds"))
engine = build / "source"
project = build / "acceptance/WatoomRecoveryProbe"
name = "WatoomRecoveryProbe"
assert plan["uid"] == 1009 and plan["gid"] == 1009
files = {}
template = engine / "Templates/TP_Blank"
for suffix in [".Target.cs", "Editor.Target.cs"]:
    original = template / ("Source/TP_Blank" + suffix)
    files["Source/" + name + suffix] = original.read_text().replace("TP_Blank", name)
files[name + ".uproject"] = json.dumps({
    "FileVersion": 3, "EngineAssociation": "",
    "Description": "Disposable engine recovery acceptance fixture",
    "Modules": [{"Name": name, "Type": "Runtime", "LoadingPhase": "Default"}],
    "DisableEnginePluginsByDefault": True
}, indent=2) + "\n"
files["Source/" + name + "/" + name + ".Build.cs"] = (
    "using UnrealBuildTool;\n"
    "public class " + name + " : ModuleRules {\n"
    " public " + name + "(ReadOnlyTargetRules Target) : base(Target) {\n"
    "  PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;\n"
    '  PublicDependencyModuleNames.AddRange(new string[] {"Core", "CoreUObject", "Engine"});\n'
    " }\n}\n")
files["Source/" + name + "/" + name + ".cpp"] = (
    '#include "Modules/ModuleManager.h"\n'
    'IMPLEMENT_PRIMARY_GAME_MODULE(FDefaultGameModuleImpl, ' + name + ', "' + name + '");\n')
files["Source/" + name + "/WatoomRecoveryVerifyCommandlet.h"] = (
    '#pragma once\n#include "CoreMinimal.h"\n#include "Commandlets/Commandlet.h"\n'
    '#include "WatoomRecoveryVerifyCommandlet.generated.h"\n'
    'UCLASS()\nclass UWatoomRecoveryVerifyCommandlet : public UCommandlet {\n GENERATED_BODY()\n'
    'public:\n UWatoomRecoveryVerifyCommandlet();\n virtual int32 Main(const FString& Params) override;\n};\n')
files["Source/" + name + "/WatoomRecoveryVerifyCommandlet.cpp"] = (
    '#include "WatoomRecoveryVerifyCommandlet.h"\n#include "Misc/EngineVersion.h"\n'
    '#include "Misc/FileHelper.h"\n#include "Misc/Paths.h"\n#include "HAL/FileManager.h"\n'
    'UWatoomRecoveryVerifyCommandlet::UWatoomRecoveryVerifyCommandlet() {\n'
    ' IsClient = false; IsServer = false; IsEditor = true; LogToConsole = true;\n}\n'
    'int32 UWatoomRecoveryVerifyCommandlet::Main(const FString& Params) {\n'
    ' const FString Version = FEngineVersion::Current().ToString();\n'
    ' const FString Directory = FPaths::ProjectSavedDir();\n'
    ' if (!IFileManager::Get().MakeDirectory(*Directory, true)) return 2;\n'
    ' if (!FFileHelper::SaveStringToFile(Version, *(Directory / TEXT("recovery-version.txt")))) return 3;\n'
    ' UE_LOG(LogTemp, Display, TEXT("WATOOM_RECOVERY_COMMANDLET_PASS version=%s"), *Version);\n'
    ' return 0;\n}\n')
receipts = {}
for rel, text in files.items():
    path = project / rel
    if path.exists():
        assert path.read_text() == text, "Preserving divergent acceptance fixture: " + str(path)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    os.chown(path, 1009, 1009)
    receipts[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
for directory, _, _ in os.walk(build / "acceptance"):
    os.chown(directory, 1009, 1009)
descriptor = project / (name + ".uproject")
result = {
    "status": "PREPARED_NOT_TESTED", "project": str(descriptor), "files": receipts,
    "build_prerequisites": ["target-UnrealEditor.json PASS", "target-ShaderCompileWorker.json PASS"],
    "compile_argv": ["bash", str(engine / "Engine/Build/BatchFiles/Linux/Build.sh"),
                     name + "Editor", "Linux", "Development", "-Project=" + str(descriptor),
                     "-NoUBA", "-MaxParallelActions=1"],
    "commandlet_argv": [str(engine / "Engine/Binaries/Linux/UnrealEditor-Cmd"),
                         str(descriptor), "-run=WatoomRecoveryVerify", "-NullRHI",
                         "-unattended", "-nosound", "-nosplash", "-nop4",
                         "-stdout", "-FullStdOutLogOutput"],
    "required_marker": "WATOOM_RECOVERY_COMMANDLET_PASS version=5.8.3",
    "required_persistent_receipt": str(project / "Saved/recovery-version.txt"),
    "execution_requirements": "UID/GID1009; original path read-only; existing bounded resource supervisor; no concurrent builds",
    "remaining": ["Real executable and shared-library validation", "C++ compile and commandlet execution",
                  "Toolkit/container access and SELinux checks", "Representative Fab asset access",
                  "Authenticated WatooM Code regression"]
}
(a.evidence / "acceptance-plan.json").write_text(json.dumps(result, indent=2))
print(json.dumps({"status": result["status"], "project": str(descriptor), "files": len(files)}))
