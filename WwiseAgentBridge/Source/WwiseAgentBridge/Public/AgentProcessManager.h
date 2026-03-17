// Copyright Wwise AI Agent Team. All Rights Reserved.
// AgentProcessManager.h — Manages the Python Agent sidecar process lifecycle.

#pragma once

#include "CoreMinimal.h"
#include "HAL/PlatformProcess.h"
#include "HAL/Runnable.h"
#include "HAL/RunnableThread.h"
#include "Containers/Ticker.h"
#include "Interfaces/IHttpRequest.h"
#include "Interfaces/IHttpResponse.h"
#include "WwiseAgentBridgeCompat.h"

DECLARE_MULTICAST_DELEGATE_OneParam(FOnAgentProcessStateChanged, bool /* bIsRunning */);

/**
 * FAgentProcessManager
 *
 * Handles:
 * - Auto-launching the Python Agent (launcher.py) in headless/server mode
 * - Heartbeat monitoring (3-5 second interval)
 * - Auto-restart on crash
 * - Graceful shutdown when UE closes
 *
 * Compatible: UE4.27 ~ UE5.7
 */
class WWISEAGENTBRIDGE_API FAgentProcessManager
{
public:
	FAgentProcessManager();
	~FAgentProcessManager();

	/** Initialize and optionally auto-launch the agent */
	void Initialize(bool bAutoLaunch = true);

	/** Tear down — stops heartbeat and kills agent process */
	void Shutdown();

	/** Manually launch the agent process */
	bool LaunchAgent();

	/** Manually stop the agent process */
	void StopAgent();

	/** Check if agent is currently running */
	bool IsAgentRunning() const;

	/** Get agent REST API base URL */
	FString GetAgentBaseUrl() const;

	/** Set the path to launcher.py */
	void SetLauncherPath(const FString& InPath);

	/** Set the agent API port */
	void SetPort(int32 InPort);

	/** Event broadcast when agent state changes */
	FOnAgentProcessStateChanged OnAgentStateChanged;

private:
	/** Heartbeat tick — called every HeartbeatInterval seconds */
#if UE_VERSION_AT_LEAST(5, 0)
	bool Heartbeat(float DeltaTime);
	FTSTicker::FDelegateHandle HeartbeatHandle;
#else
	bool Heartbeat(float DeltaTime);
	FDelegateHandle HeartbeatHandle;
#endif

	/** Send HTTP ping to agent /api/health */
	void SendHealthCheck();
	void OnHealthCheckResponse(FHttpRequestPtr Request, FHttpResponsePtr Response, bool bWasSuccessful);

	/** Attempt to restart the agent */
	void AttemptRestart();

	/** Find a Python executable path */
	FString FindPythonExecutable() const;

	/** Determine the path to launcher.py */
	FString ResolveLauncherPath() const;

	// --- State ---
	FProcHandle AgentProcessHandle;
	uint32 AgentProcessId = 0;
	FString LauncherPath;
	int32 Port = 8765;
	float HeartbeatInterval = 3.0f;
	int32 ConsecutiveFailures = 0;
	int32 MaxConsecutiveFailures = 3;
	int32 MaxRestartAttempts = 5;
	int32 RestartCount = 0;
	bool bAgentRunning = false;
	bool bShuttingDown = false;
};
