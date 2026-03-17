// Copyright Wwise AI Agent Team. All Rights Reserved.
// AgentWebSocket.h — WebSocket communication layer between UE and the Agent.

#pragma once

#include "CoreMinimal.h"
#include "IWebSocket.h"
#include "WebSocketsModule.h"
#include "WwiseAgentBridgeCompat.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonWriter.h"
#include "Serialization/JsonSerializer.h"

DECLARE_MULTICAST_DELEGATE(FOnAgentWSConnected);
DECLARE_MULTICAST_DELEGATE_OneParam(FOnAgentWSDisconnected, const FString& /* Reason */);
DECLARE_MULTICAST_DELEGATE_OneParam(FOnAgentWSError, const FString& /* Error */);
DECLARE_MULTICAST_DELEGATE_TwoParams(FOnAgentWSMessage, const FString& /* MessageType */, TSharedPtr<FJsonObject> /* Payload */);

/**
 * FAgentWebSocket
 *
 * Full-duplex WebSocket communication with the Agent API server.
 *
 * Message Protocol (JSON):
 * {
 *     "type": "asset_sync" | "chat_response" | "status" | "heartbeat" | ...,
 *     "payload": { ... },
 *     "timestamp": "ISO8601"
 * }
 *
 * Compatible: UE4.27 ~ UE5.7
 */
class WWISEAGENTBRIDGE_API FAgentWebSocket
{
public:
	FAgentWebSocket();
	~FAgentWebSocket();

	/** Connect to Agent WebSocket endpoint */
	void Connect(const FString& Url);

	/** Disconnect gracefully */
	void Disconnect();

	/** Check connection status */
	bool IsConnected() const;

	/** Send a typed JSON message to the Agent */
	void SendMessage(const FString& Type, TSharedPtr<FJsonObject> Payload);

	/** Send a raw string message */
	void SendRawMessage(const FString& Message);

	/** Send a chat message to the Agent */
	void SendChatMessage(const FString& UserMessage);

	/** Request asset sync from Agent */
	void RequestAssetSync(const FString& WwiseObjectType, const FString& WwiseObjectName);

	// --- Events ---
	FOnAgentWSConnected OnConnected;
	FOnAgentWSDisconnected OnDisconnected;
	FOnAgentWSError OnError;
	FOnAgentWSMessage OnMessage;

private:
	void HandleConnected();
	void HandleConnectionError(const FString& Error);
	void HandleClosed(int32 StatusCode, const FString& Reason, bool bWasClean);
	void HandleMessage(const FString& Message);

	/** Parse incoming JSON message */
	bool ParseMessage(const FString& RawMessage, FString& OutType, TSharedPtr<FJsonObject>& OutPayload);

	/** Attempt auto-reconnect */
	void ScheduleReconnect();

#if UE_VERSION_AT_LEAST(5, 0)
	bool ReconnectTick(float DeltaTime);
	FTSTicker::FDelegateHandle ReconnectHandle;
#else
	bool ReconnectTick(float DeltaTime);
	FDelegateHandle ReconnectHandle;
#endif

	TSharedPtr<IWebSocket> WebSocket;
	FString ServerUrl;
	bool bIsConnected = false;
	bool bAutoReconnect = true;
	int32 ReconnectAttempts = 0;
	int32 MaxReconnectAttempts = 10;
	float ReconnectDelay = 2.0f;
};
