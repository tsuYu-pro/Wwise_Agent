// Copyright Wwise AI Agent Team. All Rights Reserved.
// SWwiseAgentChatPanel.h — Native Slate chat panel for communicating with the AI Agent.

#pragma once

#include "CoreMinimal.h"
#include "Widgets/SCompoundWidget.h"
#include "Widgets/DeclarativeSyntaxSupport.h"
#include "Widgets/Input/SMultiLineEditableTextBox.h"
#include "Widgets/Input/SEditableTextBox.h"
#include "Widgets/Layout/SScrollBox.h"
#include "WwiseAgentBridgeCompat.h"

class FAgentWebSocket;

/**
 * SWwiseAgentChatPanel
 *
 * A native Slate widget providing an embedded chat interface within UE Editor.
 * Features:
 * - Scrollable message history
 * - User input text box
 * - Send button / Enter key support
 * - Connection status indicator
 * - Auto-scroll to latest message
 *
 * Compatible: UE4.27 ~ UE5.7
 */
class WWISEAGENTBRIDGE_API SWwiseAgentChatPanel : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SWwiseAgentChatPanel)
		: _WebSocket(nullptr)
	{}
		SLATE_ARGUMENT(TSharedPtr<FAgentWebSocket>, WebSocket)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

	/** Add a message to the chat display */
	void AddMessage(const FString& Sender, const FString& Message, bool bIsUser = false);

	/** Clear all messages */
	void ClearMessages();

	/** Update connection status display */
	void SetConnectionStatus(bool bConnected);

private:
	/** Handles the Send button click */
	FReply OnSendClicked();

	/** Handles Enter key in the input box */
	void OnInputTextCommitted(const FText& Text, ETextCommit::Type CommitType);

	/** Send the current input text to the Agent */
	void SendCurrentInput();

	/** Build a single chat message widget */
	TSharedRef<SWidget> BuildMessageWidget(const FString& Sender, const FString& Message, bool bIsUser);

	// --- Widgets ---
	TSharedPtr<SScrollBox> MessageScrollBox;
	TSharedPtr<SEditableTextBox> InputTextBox;
	TSharedPtr<STextBlock> ConnectionStatusText;
	TSharedPtr<SImage> ConnectionStatusIcon;

	// --- State ---
	TSharedPtr<FAgentWebSocket> WebSocket;
	bool bIsConnected = false;
};
