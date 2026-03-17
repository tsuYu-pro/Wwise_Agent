// Copyright Wwise AI Agent Team. All Rights Reserved.

#include "AgentProcessManager.h"
#include "WwiseAgentBridgeCompat.h"
#include "WwiseAgentBridgeSettings.h"
#include "HAL/PlatformProcess.h"
#include "HAL/FileManager.h"
#include "Misc/Paths.h"
#include "Misc/App.h"
#include "HttpModule.h"
#include "Interfaces/IHttpRequest.h"
#include "Interfaces/IHttpResponse.h"

#if UE_VERSION_AT_LEAST(5, 0)
#include "Containers/Ticker.h"
#else
#include "Containers/Ticker.h"
#endif

// ============================================================================
// Constructor / Destructor
// ============================================================================

FAgentProcessManager::FAgentProcessManager()
{
}

FAgentProcessManager::~FAgentProcessManager()
{
	Shutdown();
}

// ============================================================================
// Public API
// ============================================================================

void FAgentProcessManager::Initialize(bool bAutoLaunch)
{
	bShuttingDown = false;
	RestartCount = 0;
	ConsecutiveFailures = 0;

	if (bAutoLaunch)
	{
		LaunchAgent();
	}

	// Register heartbeat ticker
#if UE_VERSION_AT_LEAST(5, 0)
	HeartbeatHandle = FTSTicker::GetCoreTicker().AddTicker(
		FTSTicker::FDelegateHandle(),
		HeartbeatInterval,
		[this](float DeltaTime) -> bool { return Heartbeat(DeltaTime); }
	);
#else
	HeartbeatHandle = FTicker::GetCoreTicker().AddTicker(
		FTickerDelegate::CreateRaw(this, &FAgentProcessManager::Heartbeat),
		HeartbeatInterval
	);
#endif

	UE_LOG(LogWwiseAgentBridge, Log, TEXT("AgentProcessManager initialized. Heartbeat every %.1f sec."), HeartbeatInterval);
}

void FAgentProcessManager::Shutdown()
{
	bShuttingDown = true;

	// Remove heartbeat ticker
#if UE_VERSION_AT_LEAST(5, 0)
	if (HeartbeatHandle.IsValid())
	{
		FTSTicker::GetCoreTicker().RemoveTicker(HeartbeatHandle);
		HeartbeatHandle.Reset();
	}
#else
	if (HeartbeatHandle.IsValid())
	{
		FTicker::GetCoreTicker().RemoveTicker(HeartbeatHandle);
		HeartbeatHandle.Reset();
	}
#endif

	StopAgent();

	UE_LOG(LogWwiseAgentBridge, Log, TEXT("AgentProcessManager shutdown complete."));
}

bool FAgentProcessManager::LaunchAgent()
{
	if (bAgentRunning)
	{
		UE_LOG(LogWwiseAgentBridge, Warning, TEXT("Agent is already running (PID: %u)."), AgentProcessId);
		return true;
	}

	FString PythonExe = FindPythonExecutable();
	if (PythonExe.IsEmpty())
	{
		UE_LOG(LogWwiseAgentBridge, Error, TEXT("Cannot find Python executable. Please configure in Editor Preferences."));
		return false;
	}

	FString ResolvedLauncherPath = ResolveLauncherPath();
	if (ResolvedLauncherPath.IsEmpty() || !FPaths::FileExists(ResolvedLauncherPath))
	{
		UE_LOG(LogWwiseAgentBridge, Error, TEXT("Cannot find launcher.py at: %s"), *ResolvedLauncherPath);
		return false;
	}

	// Build command line: python launcher.py --headless --port 8765
	FString Args = FString::Printf(TEXT("\"%s\" --headless --port %d"), *ResolvedLauncherPath, Port);

	// Inject CodeBuddy API Key as environment variable if configured
	const UWwiseAgentBridgeSettings* Settings = UWwiseAgentBridgeSettings::GetSettings();
	if (Settings && !Settings->CodeBuddyApiKey.IsEmpty())
	{
		FPlatformMisc::SetEnvironmentVar(TEXT("CODEBUDDY_API_KEY"), *Settings->CodeBuddyApiKey);
		UE_LOG(LogWwiseAgentBridge, Log, TEXT("Injected CODEBUDDY_API_KEY environment variable."));
	}
	if (Settings && !Settings->CodeBuddyEnvironment.IsEmpty())
	{
		FPlatformMisc::SetEnvironmentVar(TEXT("CODEBUDDY_INTERNET_ENVIRONMENT"), *Settings->CodeBuddyEnvironment);
		UE_LOG(LogWwiseAgentBridge, Log, TEXT("Injected CODEBUDDY_INTERNET_ENVIRONMENT=%s"), *Settings->CodeBuddyEnvironment);
	}

	UE_LOG(LogWwiseAgentBridge, Log, TEXT("Launching Agent: %s %s"), *PythonExe, *Args);

	void* PipeRead = nullptr;
	void* PipeWrite = nullptr;

	// FPlatformProcess::CreateProc is consistent across UE4.27~UE5.7
	AgentProcessHandle = FPlatformProcess::CreateProc(
		*PythonExe,             // Executable
		*Args,                  // Arguments
		false,                  // bLaunchDetached
		true,                   // bLaunchHidden
		true,                   // bLaunchReallyHidden
		&AgentProcessId,        // OutProcessID
		0,                      // PriorityModifier
		nullptr,                // OptionalWorkingDirectory
		PipeWrite,              // PipeWriteChild (stdout)
		PipeRead                // PipeReadChild  (stdin)
	);

	if (!AgentProcessHandle.IsValid())
	{
		UE_LOG(LogWwiseAgentBridge, Error, TEXT("Failed to create Agent process."));
		return false;
	}

	bAgentRunning = true;
	UE_LOG(LogWwiseAgentBridge, Log, TEXT("Agent launched successfully (PID: %u)."), AgentProcessId);

	OnAgentStateChanged.Broadcast(true);
	return true;
}

void FAgentProcessManager::StopAgent()
{
	if (!bAgentRunning && !AgentProcessHandle.IsValid())
	{
		return;
	}

	UE_LOG(LogWwiseAgentBridge, Log, TEXT("Stopping Agent process (PID: %u)..."), AgentProcessId);

	// Try graceful shutdown via HTTP first
	if (bAgentRunning)
	{
		TSharedRef<IHttpRequest
#if UE_VERSION_AT_LEAST(5, 0)
		, ESPMode::ThreadSafe
#endif
		> Request = WAB_CREATE_HTTP_REQUEST();
		Request->SetURL(FString::Printf(TEXT("http://127.0.0.1:%d/api/shutdown"), Port));
		Request->SetVerb(TEXT("POST"));
		Request->SetHeader(TEXT("Content-Type"), TEXT("application/json"));
		Request->ProcessRequest();

		// Give it a moment
		FPlatformProcess::Sleep(0.5f);
	}

	// Force terminate if still running
	if (FPlatformProcess::IsProcRunning(AgentProcessHandle))
	{
		FPlatformProcess::TerminateProc(AgentProcessHandle, true);
		UE_LOG(LogWwiseAgentBridge, Log, TEXT("Agent process force-terminated."));
	}

	FPlatformProcess::CloseProc(AgentProcessHandle);
	AgentProcessHandle.Reset();
	AgentProcessId = 0;
	bAgentRunning = false;

	OnAgentStateChanged.Broadcast(false);
}

bool FAgentProcessManager::IsAgentRunning() const
{
	return bAgentRunning;
}

FString FAgentProcessManager::GetAgentBaseUrl() const
{
	return FString::Printf(TEXT("http://127.0.0.1:%d"), Port);
}

void FAgentProcessManager::SetLauncherPath(const FString& InPath)
{
	LauncherPath = InPath;
}

void FAgentProcessManager::SetPort(int32 InPort)
{
	Port = FMath::Clamp(InPort, 1024, 65535);
}

// ============================================================================
// Heartbeat
// ============================================================================

bool FAgentProcessManager::Heartbeat(float DeltaTime)
{
	if (bShuttingDown)
	{
		return false; // Stop ticking
	}

	// Check if process is still alive
	if (AgentProcessHandle.IsValid() && !FPlatformProcess::IsProcRunning(AgentProcessHandle))
	{
		UE_LOG(LogWwiseAgentBridge, Warning, TEXT("Agent process is no longer running!"));
		bAgentRunning = false;
		OnAgentStateChanged.Broadcast(false);
		AttemptRestart();
		return true;
	}

	// Send HTTP health check
	if (bAgentRunning)
	{
		SendHealthCheck();
	}

	return true; // Continue ticking
}

void FAgentProcessManager::SendHealthCheck()
{
	TSharedRef<IHttpRequest
#if UE_VERSION_AT_LEAST(5, 0)
	, ESPMode::ThreadSafe
#endif
	> Request = WAB_CREATE_HTTP_REQUEST();
	Request->SetURL(FString::Printf(TEXT("http://127.0.0.1:%d/api/health"), Port));
	Request->SetVerb(TEXT("GET"));
	Request->SetHeader(TEXT("Content-Type"), TEXT("application/json"));
	Request->OnProcessRequestComplete().BindRaw(this, &FAgentProcessManager::OnHealthCheckResponse);
	Request->ProcessRequest();
}

void FAgentProcessManager::OnHealthCheckResponse(
	FHttpRequestPtr Request, FHttpResponsePtr Response, bool bWasSuccessful)
{
	if (bShuttingDown) return;

	if (bWasSuccessful && Response.IsValid() && Response->GetResponseCode() == 200)
	{
		ConsecutiveFailures = 0;
		if (!bAgentRunning)
		{
			bAgentRunning = true;
			OnAgentStateChanged.Broadcast(true);
			UE_LOG(LogWwiseAgentBridge, Log, TEXT("Agent health check recovered."));
		}
	}
	else
	{
		ConsecutiveFailures++;
		UE_LOG(LogWwiseAgentBridge, Warning, TEXT("Agent health check failed (%d/%d)."),
			ConsecutiveFailures, MaxConsecutiveFailures);

		if (ConsecutiveFailures >= MaxConsecutiveFailures)
		{
			bAgentRunning = false;
			OnAgentStateChanged.Broadcast(false);
			AttemptRestart();
		}
	}
}

void FAgentProcessManager::AttemptRestart()
{
	if (bShuttingDown) return;

	if (RestartCount >= MaxRestartAttempts)
	{
		UE_LOG(LogWwiseAgentBridge, Error,
			TEXT("Agent has crashed %d times. Giving up auto-restart. Please restart manually."),
			RestartCount);
		return;
	}

	RestartCount++;
	ConsecutiveFailures = 0;

	UE_LOG(LogWwiseAgentBridge, Log, TEXT("Attempting Agent restart (%d/%d)..."),
		RestartCount, MaxRestartAttempts);

	// Clean up old process handle
	if (AgentProcessHandle.IsValid())
	{
		FPlatformProcess::CloseProc(AgentProcessHandle);
		AgentProcessHandle.Reset();
	}

	// Wait a bit before restarting
	FPlatformProcess::Sleep(1.0f);

	LaunchAgent();
}

// ============================================================================
// Helpers
// ============================================================================

FString FAgentProcessManager::FindPythonExecutable() const
{
	// 1. Check configured path
	// (will be set from Settings if provided)

	// 2. Try system Python
#if PLATFORM_WINDOWS
	// Try common locations
	TArray<FString> Candidates = {
		TEXT("python"),
		TEXT("python3"),
		TEXT("py"),
	};

	for (const FString& Candidate : Candidates)
	{
		FString FullPath = FPlatformProcess::ExecutablePath();
		// Just use the name and let the system PATH resolve it
		// Verify by checking if it exists
		return Candidate;
	}
	return TEXT("python");
#elif PLATFORM_MAC || PLATFORM_LINUX
	return TEXT("python3");
#else
	return TEXT("python");
#endif
}

FString FAgentProcessManager::ResolveLauncherPath() const
{
	// 1. If explicitly configured, use that
	if (!LauncherPath.IsEmpty())
	{
		return LauncherPath;
	}

	// 2. Try relative to plugin directory
	FString PluginDir = FPaths::ConvertRelativePathToFull(
		FPaths::Combine(FPaths::ProjectPluginsDir(), TEXT("WwiseAgentBridge")));
	FString LauncherCandidate = FPaths::Combine(PluginDir, TEXT(".."), TEXT(".."), TEXT("launcher.py"));
	FPaths::NormalizeFilename(LauncherCandidate);
	if (FPaths::FileExists(LauncherCandidate))
	{
		return LauncherCandidate;
	}

	// 3. Try relative to project root
	LauncherCandidate = FPaths::Combine(FPaths::ProjectDir(), TEXT("WwiseAgent"), TEXT("launcher.py"));
	if (FPaths::FileExists(LauncherCandidate))
	{
		return LauncherCandidate;
	}

	// 4. Try parent of project dir (common in development)
	LauncherCandidate = FPaths::Combine(FPaths::ProjectDir(), TEXT(".."), TEXT("Wwise_Agent"), TEXT("launcher.py"));
	FPaths::NormalizeFilename(LauncherCandidate);
	if (FPaths::FileExists(LauncherCandidate))
	{
		return LauncherCandidate;
	}

	UE_LOG(LogWwiseAgentBridge, Warning, TEXT("Could not auto-detect launcher.py path. Please configure in Editor Preferences."));
	return FString();
}
