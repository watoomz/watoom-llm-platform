using UnrealBuildTool;

public class WatooMCombat : ModuleRules
{
	public WatooMCombat(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PublicDependencyModuleNames.AddRange(new string[]
		{
			"Core", "CoreUObject", "Engine", "InputCore", "EnhancedInput", "AnimGraphRuntime", "GameplayAbilities", "GameplayTags", "GameplayTasks", "Niagara", "NetCore"
		});
	}
}
