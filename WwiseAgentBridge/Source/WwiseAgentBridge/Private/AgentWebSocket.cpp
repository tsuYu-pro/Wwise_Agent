// Copyright Wwise AI Agent Team. All Rights Reserved.

#include "AgentWebSocket.h"
#include "WwiseAgentBridgeCompat.h"
#include "WebSocketsModule.h"
#include "Misc/DateTime.h"

#if UE_VERSION_AT_LEAST(5, 0)
#include "Containers/Ticker.h"
#else
#include "Containers/Ticker.h"
#endif

// ============================================================================
// Constructor / Destructor
// ============================================================================

FAgentWebSocket::FAgentWebSocket()
{
	// Ensure WebSockets module is loaded
	if (!FModuleManager::Get().IsModuleLoaded("WebSockets"))
	{
		FModuleManager::Get().LoadModule("WebSockets");
	}
}

FAgentWebSocket::~FAgentWebSocket()
{
	Disconnect();
}

// ============================================================================
// Public API
// ============================================================================

void FAgentWebSocket::Connect(const FString& Url)
{
	if (bIsConnected && WebSocket.IsValid())
	{
		UE_LOG(LogWwiseAgentBridge, Warning, TEXT("WebSocket already connected to %s"), *ServerUrl);
		return;
	}

	ServerUrl = Url;
	ReconnectAttempts = 0;

	UE_LOG(LogWwiseAgentBridge, Log, TEXT("Connecting WebSocket to %s"), *Url);

	// Create the WebSocket — API is identical UE4.27~UE5.7
	const FString Protocol = TEXT("ws");
	TMap<FString, FString> Headers;
	Headers.Add(TEXT("User-Agent"), TEXT("WwiseAgentBridge-UE"));

	WebSocket = FWebSocketsModule::Get().CreateWebSocket(Url, Protocol, Headers);

	if (!WebSocket.IsValid())
	{
		UE_LOG(LogWwiseAgentBridge, Error, TEXT("Failed to create WebSocket instance."));
		return;
	}

	// Bind delegates
	WebSocket->OnConnected().AddRaw(this, &FAgentWebSocket::HandleConnected);
	WebSocket->OnConnectionError().AddRaw(this, &FAgentWebSocket::HandleConnectionError);
	WebSocket->OnClosed().AddRaw(this, &FAgentWebSocket::HandleClosed);
	WebSocket->OnMessage().AddRaw(this, &FAgentWebSocket::HandleMessage);

	WebSocket->Connect();
}

void FAgentWebSocket::Disconnect()
{
	bAutoReconnect = false;

	// Cancel any pending reconnect
#if UE_VERSION_AT_LEAST(5, 0)
	if (ReconnectHandle.IsValid())
	{
		FTSTicker::GetCoreTicker().RemoveTicker(ReconnectHandle);
		ReconnectHandle.Reset();
	}
#else
	if (ReconnectHandle.IsValid())
	{
		FTicker::GetCoreTicker().RemoveTicker(ReconnectHandle);
		ReconnectHandle.Reset();
	}
#endif

	if (WebSocket.IsValid())
	{
		if (WebSocket->IsConnected())
		{
			WebSocket->Close();
		}
		WebSocket.Reset();
	}

	bIsConnected = false;
}

bool FAgentWebSocket::IsConnected() const
{
	return bIsConnected && WebSocket.IsValid() && WebSocket->IsConnected();
}

void FAgentWebSocket::SendMessage(const FString& Type, TSharedPtr<FJsonObject> Payload)
{
	if (!IsConnected())
	{
		UE_LOG(LogWwiseAgentBridge, Warning, TEXT("Cannot send message — WebSocket not connected."));
		return;
	}

	TSharedPtr<FJsonObject> Envelope = MakeShared<FJsonObject>();
	Envelope->SetStringField(TEXT("type"), Type);
	if (Payload.IsValid())
	{
		Envelope->SetObjectField(TEXT("payload"), Payload);
	}
	Envelope->SetStringField(TEXT("timestamp"), FDateTime::UtcNow().ToIso8601());

	FString OutputString;
	TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&OutputString);
	FJsonSerializer::Serialize(Envelope.ToSharedRef(), Writer);

	WebSocket->Send(OutputString);
}

void FAgentWebSocket::SendRawMessage(const FString& Message)
{
	if (!IsConnected())
	{
		UE_LOG(LogWwiseAgentBridge, Warning, TEXT("Cannot send raw message — WebSocket not connected."));
		return;
	}
	WebSocket->Send(Message);
}

void FAgentWebSocket::SendChatMessage(const FString& UserMessage)
{
	TSharedPtr<FJsonObject> Payload = MakeShared<FJsonObject>();
	Payload->SetStringField(TEXT("message"), UserMessage);
	SendMessage(TEXT("chat"), Payload);
}

void FAgentWebSocket::RequestAssetSync(const FString& WwiseObjectType, const FString& WwiseObjectName)
{
	TSharedPtr<FJsonObject> Payload = MakeShared<FJsonObject>();
	Payload->SetStringField(TEXT("object_type"), WwiseObjectType);
	Payload->SetStringField(TEXT("object_name"), WwiseObjectName);
	Payload->SetStringField(TEXT("action"), TEXT("sync_to_ue"));
	SendMessage(TEXT("asset_sync_request"), Payload);
}

// ============================================================================
// WebSocket Event Handlers
// ============================================================================

void FAgentWebSocket::HandleConnected()
{
	bIsConnected = true;
	ReconnectAttempts = 0;

	UE_LOG(LogWwiseAgentBridge, Log, TEXT("WebSocket connected to %s"), *ServerUrl);
	OnConnected.Broadcast();
}

void FAgentWebSocket::HandleConnectionError(const FString& Error)
{
	UE_LOG(LogWwiseAgentBridge, Error, TEXT("WebSocket connection error: %s"), *Error);
	bIsConnected = false;
	OnError.Broadcast(Error);

	if (bAutoReconnect)
	{
		ScheduleReconnect();
	}
}

void FAgentWebSocket::HandleClosed(int32 StatusCode, const FString& Reason, bool bWasClean)
{
	bIsConnected = false;
	FString LogReason = Reason.IsEmpty() ? TEXT("(no reason)") : Reason;

	UE_LOG(LogWwiseAgentBridge, Log, TEXT("WebSocket closed — Code: %d, Reason: %s, Clean: %s"),
		StatusCode, *LogReason, bWasClean ? TEXT("Yes") : TEXT("No"));

	OnDisconnected.Broadcast(LogReason);

	if (bAutoReconnect && !bWasClean)
	{
		ScheduleReconnect();
	}
}

void FAgentWebSocket::HandleMessage(const FString& Message)
{
	FString Type;
	TSharedPtr<FJsonObject> Payload;

	if (ParseMessage(Message, Type, Payload))
	{
		OnMessage.Broadcast(Type, Payload);
	}
	else
	{
		UE_LOG(LogWwiseAgentBridge, Warning, TEXT("Received non-JSON WebSocket message: %s"),
			*Message.Left(200));
	}
}

// ============================================================================
// Helpers
// ============================================================================

bool FAgentWebSocket::ParseMessage(const FString& RawMessage, FString& OutType, TSharedPtr<FJsonObject>& OutPayload)
{
	TSharedPtr<FJsonObject> JsonObj;
	TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(RawMessage);

	if (!FJsonSerializer::Deserialize(Reader, JsonObj) || !JsonObj.IsValid())
	{
		return false;
	}

	OutType = JsonObj->GetStringField(TEXT("type"));
	JsonObj->TryGetObjectField(TEXT("payload"), OutPayload);

	return true;
}

void FAgentWebSocket::ScheduleReconnect()
{
	if (ReconnectAttempts >= MaxReconnectAttempts)
	{
		UE_LOG(LogWwiseAgentBridge, Error, TEXT("Max reconnect attempts (%d) reached. Giving up."), MaxReconnectAttempts);
		return;
	}

	ReconnectAttempts++;
	float Delay = ReconnectDelay * FMath::Min(ReconnectAttempts, 5); // Exponential-ish backoff

	UE_LOG(LogWwiseAgentBridge, Log, TEXT("Scheduling WebSocket reconnect in %.1f sec (attempt %d/%d)"),
		Delay, ReconnectAttempts, MaxReconnectAttempts);

#if UE_VERSION_AT_LEAST(5, 0)
	ReconnectHandle = FTSTicker::GetCoreTicker().AddTicker(
		FTSTicker::FDelegateHandle(),
		Delay,
		[this](float) -> bool { return ReconnectTick(0.0f); }
	);
#else
	ReconnectHandle = FTicker::GetCoreTicker().AddTicker(
		FTickerDelegate::CreateRaw(this, &FAgentWebSocket::ReconnectTick),
		Delay
	);
#endif
}

bool FAgentWebSocket::ReconnectTick(float DeltaTime)
{
	if (!bAutoReconnect) return false;

	UE_LOG(LogWwiseAgentBridge, Log, TEXT("Reconnecting WebSocket to %s..."), *ServerUrl);

	// Clean up old socket
	if (WebSocket.IsValid())
	{
		WebSocket.Reset();
	}

	// Reconnect
	Connect(ServerUrl);

	return false; // One-shot
}
