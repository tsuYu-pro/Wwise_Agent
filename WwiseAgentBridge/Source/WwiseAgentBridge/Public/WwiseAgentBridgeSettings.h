// Copyright Wwise AI Agent Team. All Rights Reserved.
// WwiseAgentBridgeSettings.h — Plugin configuration exposed in Editor Preferences.

#pragma once

#include "CoreMinimal.h"
#include "Engine/DeveloperSettings.h"
#include "WwiseAgentBridgeSettings.generated.h"

/**
 * UWwiseAgentBridgeSettings
 *
 * Configuration for the WwiseAgentBridge plugin.
 * Accessible via Editor Preferences > Plugins > Wwise Agent Bridge.
 *
 * Compatible: UE4.27 ~ UE5.7
 */
UCLASS(config = EditorPerUser, defaultconfig, meta = (DisplayName = "Wwise Agent Bridge"))
class WWISEAGENTBRIDGE_API UWwiseAgentBridgeSettings : public UDeveloperSettings
{
	GENERATED_BODY()

public:
	UWwiseAgentBridgeSettings();

	// --- Process Management ---

	/** Whether to auto-launch the Agent when UE Editor starts */
	UPROPERTY(config, EditAnywhere, Category = "Process", meta = (DisplayName = "Auto-Launch Agent on Editor Start"))
	bool bAutoLaunchAgent = true;

	/** Path to launcher.py (leave empty for auto-detection relative to plugin) */
	UPROPERTY(config, EditAnywhere, Category = "Process", meta = (DisplayName = "Launcher Script Path"))
	FString LauncherScriptPath;

	/** Path to Python executable (leave empty for auto-detection) */
	UPROPERTY(config, EditAnywhere, Category = "Process", meta = (DisplayName = "Python Executable Path"))
	FString PythonExecutablePath;

	/** Heartbeat interval in seconds */
	UPROPERTY(config, EditAnywhere, Category = "Process", meta = (DisplayName = "Heartbeat Interval (seconds)", ClampMin = "1.0", ClampMax = "30.0"))
	float HeartbeatInterval = 3.0f;

	/** Maximum restart attempts before giving up */
	UPROPERTY(config, EditAnywhere, Category = "Process", meta = (DisplayName = "Max Restart Attempts", ClampMin = "0", ClampMax = "20"))
	int32 MaxRestartAttempts = 5;

	// --- Communication ---

	/** Agent REST API / WebSocket port */
	UPROPERTY(config, EditAnywhere, Category = "Communication", meta = (DisplayName = "Agent Port", ClampMin = "1024", ClampMax = "65535"))
	int32 AgentPort = 8765;

	/** Enable WebSocket full-duplex communication (recommended) */
	UPROPERTY(config, EditAnywhere, Category = "Communication", meta = (DisplayName = "Use WebSocket"))
	bool bUseWebSocket = true;

	/** WebSocket auto-reconnect on disconnect */
	UPROPERTY(config, EditAnywhere, Category = "Communication", meta = (DisplayName = "Auto-Reconnect WebSocket"))
	bool bAutoReconnect = true;

	// --- Asset Synchronization ---

	/** Enable automatic Wwise → UE asset sync */
	UPROPERTY(config, EditAnywhere, Category = "Asset Sync", meta = (DisplayName = "Enable Asset Synchronization"))
	bool bEnableAssetSync = true;

	/** Default folder for synced assets (relative to /Game/) */
	UPROPERTY(config, EditAnywhere, Category = "Asset Sync", meta = (DisplayName = "Default Sync Target Folder"))
	FString DefaultSyncFolder = TEXT("/Game/WwiseSync");

	// --- UI ---

	/** Show Agent status indicator in the editor status bar */
	UPROPERTY(config, EditAnywhere, Category = "UI", meta = (DisplayName = "Show Status Bar Indicator"))
	bool bShowStatusBarIndicator = true;

	// --- AI Provider ---

	/**
	 * CodeBuddy API Key (CODEBUDDY_API_KEY).
	 * Platform authentication credential used by the Claude Code Internal (claude-internal) CLI tool.
	 * Obtain from: https://www.codebuddy.ai/profile/keys
	 * When set, it will be injected as CODEBUDDY_API_KEY environment variable when launching the Agent.
	 *
	 * Usage: claude-internal -p --output-format stream-json --verbose "prompt"
	 * Install CLI: npm install -g --registry=https://mirrors.tencent.com/npm @tencent/claude-code-internal
	 * Docs: https://iwiki.woa.com/p/4015845000
	 */
	UPROPERTY(config, EditAnywhere, Category = "AI Provider", meta = (DisplayName = "CodeBuddy API Key", PasswordField = true))
	FString CodeBuddyApiKey;

	/**
	 * CodeBuddy environment type. Leave empty for global/overseas version.
	 * Set to "internal" for China version, "ioa" for iOA version.
	 * Injected as CODEBUDDY_INTERNET_ENVIRONMENT when launching the Agent.
	 */
	UPROPERTY(config, EditAnywhere, Category = "AI Provider", meta = (DisplayName = "CodeBuddy Environment"))
	FString CodeBuddyEnvironment;

	/** Get singleton settings object */
	static const UWwiseAgentBridgeSettings* GetSettings();
};
