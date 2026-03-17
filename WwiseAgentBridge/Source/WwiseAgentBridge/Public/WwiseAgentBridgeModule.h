// Copyright Wwise AI Agent Team. All Rights Reserved.
// WwiseAgentBridgeModule.h — Main plugin module (Editor-only)

#pragma once

#include "CoreMinimal.h"
#include "Modules/ModuleManager.h"

class FWwiseAgentBridgeModule : public IModuleInterface
{
public:
	/** IModuleInterface */
	virtual void StartupModule() override;
	virtual void ShutdownModule() override;

	/** Get the singleton module instance */
	static FWwiseAgentBridgeModule& Get();
	static bool IsAvailable();

private:
	void RegisterMenuExtensions();
	void UnregisterMenuExtensions();
	void RegisterTabSpawner();
	void UnregisterTabSpawner();

	/** Handles for registered delegates */
	FDelegateHandle ToolMenusHandle;
};
