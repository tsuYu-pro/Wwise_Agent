// Copyright Wwise AI Agent Team. All Rights Reserved.

using UnrealBuildTool;

public class WwiseAgentBridge : ModuleRules
{
	public WwiseAgentBridge(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(new string[]
		{
			"Core",
			"CoreUObject",
			"Engine",
			"InputCore",
			"Slate",
			"SlateCore",
			"EditorStyle",
			"UnrealEd",
			"LevelEditor",
			"Projects",
			"Http",
			"Json",
			"JsonUtilities",
			"WebSockets",
		});

		PrivateDependencyModuleNames.AddRange(new string[]
		{
			"ToolMenus",
			"EditorSubsystem",
			"StatusBar",
		});

		// UE5.0+ modules
		if (Target.Version.MajorVersion >= 5)
		{
			PrivateDependencyModuleNames.Add("EditorFramework");
		}

		// UE5.4+ split these into standalone modules
		if (Target.Version.MajorVersion > 5 ||
		    (Target.Version.MajorVersion == 5 && Target.Version.MinorVersion >= 4))
		{
			PrivateDependencyModuleNames.Add("WorkspaceMenuStructure");
			PrivateDependencyModuleNames.Add("DeveloperSettings");
		}

		// Wwise Integration (optional — only if present in project)
		// Uncomment the following lines if your project uses the Wwise UE Integration plugin:
		// PublicDependencyModuleNames.Add("AkAudio");
		// PrivateDependencyModuleNames.Add("AudiokineticTools");

		// Ensure we compile as editor-only
		if (Target.bBuildEditor)
		{
			// All good — this module is editor-only
		}
	}
}
