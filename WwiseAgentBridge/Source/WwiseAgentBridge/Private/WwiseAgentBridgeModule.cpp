// Copyright Wwise AI Agent Team. All Rights Reserved.

#include "WwiseAgentBridgeModule.h"
#include "WwiseAgentBridgeCompat.h"
#include "WwiseAgentBridgeSettings.h"
#include "AgentProcessManager.h"
#include "AgentWebSocket.h"
#include "WwiseAssetSynchronizer.h"
#include "SWwiseAgentChatPanel.h"

#include "Framework/Docking/TabManager.h"
#include "Widgets/Docking/SDockTab.h"
#include "WorkspaceMenuStructure.h"
#include "WorkspaceMenuStructureModule.h"
#include "ToolMenus.h"
#include "LevelEditor.h"

#if UE_VERSION_AT_LEAST(5, 0)
#include "Styling/AppStyle.h"
#else
#include "EditorStyleSet.h"
#endif

DEFINE_LOG_CATEGORY(LogWwiseAgentBridge);

static const FName WwiseAgentChatTabName(TEXT("WwiseAgentChat"));

// Singleton instances (module-lifetime)
static TUniquePtr<FAgentProcessManager> GProcessManager;
static TSharedPtr<FAgentWebSocket> GWebSocket;
static TUniquePtr<FWwiseAssetSynchronizer> GAssetSync;

// ============================================================================
// Module Startup / Shutdown
// ============================================================================

void FWwiseAgentBridgeModule::StartupModule()
{
	UE_LOG(LogWwiseAgentBridge, Log, TEXT("WwiseAgentBridge — Starting up (Engine %d.%d)"),
		ENGINE_MAJOR_VERSION, ENGINE_MINOR_VERSION);

	const UWwiseAgentBridgeSettings* Settings = UWwiseAgentBridgeSettings::GetSettings();

	// 1. Register Tab Spawner (Chat Panel)
	RegisterTabSpawner();

	// 2. Register Tool Menu extensions
	if (UToolMenus::IsToolMenuUIEnabled())
	{
		UToolMenus::RegisterStartupCallback(
			FSimpleMulticastDelegate::FDelegate::CreateRaw(this, &FWwiseAgentBridgeModule::RegisterMenuExtensions));
	}

	// 3. Initialize Process Manager
	GProcessManager = MakeUnique<FAgentProcessManager>();
	if (Settings)
	{
		if (!Settings->LauncherScriptPath.IsEmpty())
		{
			GProcessManager->SetLauncherPath(Settings->LauncherScriptPath);
		}
		GProcessManager->SetPort(Settings->AgentPort);
	}
	GProcessManager->Initialize(Settings ? Settings->bAutoLaunchAgent : true);

	// 4. Initialize WebSocket
	GWebSocket = MakeShared<FAgentWebSocket>();

	// 5. Initialize Asset Synchronizer
	GAssetSync = MakeUnique<FWwiseAssetSynchronizer>();
	GAssetSync->Initialize();
	if (Settings)
	{
		GAssetSync->SetDefaultTargetFolder(Settings->DefaultSyncFolder);
	}

	// 6. Wire up WebSocket -> Asset Sync
	GWebSocket->OnMessage.AddLambda([](const FString& Type, TSharedPtr<FJsonObject> Payload)
	{
		if (Type == TEXT("asset_sync") && GAssetSync.IsValid())
		{
			GAssetSync->ProcessSyncMessage(Payload);
		}
	});

	// 7. Connect WebSocket when process is running
	GProcessManager->OnAgentStateChanged.AddLambda([Settings](bool bIsRunning)
	{
		if (bIsRunning && GWebSocket.IsValid())
		{
			int32 Port = Settings ? Settings->AgentPort : 8765;
			FString WsUrl = FString::Printf(TEXT("ws://127.0.0.1:%d/ws"), Port);
			GWebSocket->Connect(WsUrl);
		}
		else if (!bIsRunning && GWebSocket.IsValid())
		{
			GWebSocket->Disconnect();
		}
	});

	UE_LOG(LogWwiseAgentBridge, Log, TEXT("WwiseAgentBridge — Startup complete."));
}

void FWwiseAgentBridgeModule::ShutdownModule()
{
	UE_LOG(LogWwiseAgentBridge, Log, TEXT("WwiseAgentBridge — Shutting down."));

	UnregisterTabSpawner();
	UnregisterMenuExtensions();

	if (GWebSocket.IsValid())
	{
		GWebSocket->Disconnect();
		GWebSocket.Reset();
	}

	GAssetSync.Reset();

	if (GProcessManager.IsValid())
	{
		GProcessManager->Shutdown();
		GProcessManager.Reset();
	}

	UE_LOG(LogWwiseAgentBridge, Log, TEXT("WwiseAgentBridge — Shutdown complete."));
}

FWwiseAgentBridgeModule& FWwiseAgentBridgeModule::Get()
{
	return FModuleManager::LoadModuleChecked<FWwiseAgentBridgeModule>("WwiseAgentBridge");
}

bool FWwiseAgentBridgeModule::IsAvailable()
{
	return FModuleManager::Get().IsModuleLoaded("WwiseAgentBridge");
}

// ============================================================================
// Tab Spawner
// ============================================================================

void FWwiseAgentBridgeModule::RegisterTabSpawner()
{
	WAB_GLOBAL_TAB_MANAGER->RegisterNomadTabSpawner(
		WwiseAgentChatTabName,
		FOnSpawnTab::CreateLambda([](const FSpawnTabArgs& Args) -> TSharedRef<SDockTab>
		{
			TSharedRef<SWwiseAgentChatPanel> ChatPanel = SNew(SWwiseAgentChatPanel)
				.WebSocket(GWebSocket);

			return SNew(SDockTab)
				.TabRole(ETabRole::NomadTab)
				.Label(FText::FromString(TEXT("Wwise Agent")))
				[
					ChatPanel
				];
		}))
		.SetDisplayName(FText::FromString(TEXT("Wwise AI Agent")))
		.SetTooltipText(FText::FromString(TEXT("Open the Wwise AI Agent chat panel")))
		.SetIcon(FSlateIcon(WAB_GET_APP_STYLE_SET_NAME(), "LevelEditor.Tabs.Details"))
		.SetGroup(WorkspaceMenu::GetMenuStructure().GetToolsCategory());
}

void FWwiseAgentBridgeModule::UnregisterTabSpawner()
{
	if (FSlateApplication::IsInitialized())
	{
		WAB_GLOBAL_TAB_MANAGER->UnregisterNomadTabSpawner(WwiseAgentChatTabName);
	}
}

// ============================================================================
// Menu Extensions
// ============================================================================

void FWwiseAgentBridgeModule::RegisterMenuExtensions()
{
	// Add a menu entry under Window > Wwise Agent
	UToolMenu* WindowMenu = UToolMenus::Get()->ExtendMenu("LevelEditor.MainMenu.Window");
	if (WindowMenu)
	{
		FToolMenuSection& Section = WindowMenu->FindOrAddSection("WwiseAgent");
		Section.Label = FText::FromString(TEXT("Wwise Agent"));

		Section.AddMenuEntry(
			"OpenWwiseAgentChat",
			FText::FromString(TEXT("Wwise AI Agent Chat")),
			FText::FromString(TEXT("Open the Wwise AI Agent chat panel")),
			FSlateIcon(WAB_GET_APP_STYLE_SET_NAME(), "LevelEditor.Tabs.Details"),
			FUIAction(FExecuteAction::CreateLambda([]()
			{
				WAB_GLOBAL_TAB_MANAGER->TryInvokeTab(WwiseAgentChatTabName);
			}))
		);
	}

	// Add right-click context menu entry in Content Browser
	UToolMenu* ContentBrowserContextMenu = UToolMenus::Get()->ExtendMenu("ContentBrowser.AssetContextMenu");
	if (ContentBrowserContextMenu)
	{
		FToolMenuSection& Section = ContentBrowserContextMenu->FindOrAddSection("WwiseAgent");
		Section.Label = FText::FromString(TEXT("Wwise Agent"));

		Section.AddMenuEntry(
			"SendToWwiseAgent",
			FText::FromString(TEXT("Send to Wwise Agent")),
			FText::FromString(TEXT("Send this asset to Wwise AI Agent for analysis")),
			FSlateIcon(),
			FUIAction(FExecuteAction::CreateLambda([]()
			{
				// TODO: Implement — get selected assets and send to Agent
				UE_LOG(LogWwiseAgentBridge, Log, TEXT("SendToWwiseAgent — Context menu action triggered."));
			}))
		);
	}
}

void FWwiseAgentBridgeModule::UnregisterMenuExtensions()
{
	if (UToolMenus* ToolMenus = UToolMenus::TryGet())
	{
		ToolMenus->UnregisterOwnerByName("WwiseAgentBridge");
	}
}

// ============================================================================
// Module Implementation Macro
// ============================================================================

IMPLEMENT_MODULE(FWwiseAgentBridgeModule, WwiseAgentBridge)
