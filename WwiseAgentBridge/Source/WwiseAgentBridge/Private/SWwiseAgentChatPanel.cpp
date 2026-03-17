// Copyright Wwise AI Agent Team. All Rights Reserved.

#include "SWwiseAgentChatPanel.h"
#include "WwiseAgentBridgeCompat.h"
#include "AgentWebSocket.h"

#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SSplitter.h"
#include "Widgets/Layout/SSpacer.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Text/STextBlock.h"
#include "Widgets/Images/SImage.h"
#include "Widgets/SBoxPanel.h"

// ============================================================================
// Construct
// ============================================================================

void SWwiseAgentChatPanel::Construct(const FArguments& InArgs)
{
	WebSocket = InArgs._WebSocket;

	// Wire up WebSocket message handler
	if (WebSocket.IsValid())
	{
		WebSocket->OnMessage.AddLambda([this](const FString& Type, TSharedPtr<FJsonObject> Payload)
		{
			if (Type == TEXT("chat_response") && Payload.IsValid())
			{
				FString Response = Payload->GetStringField(TEXT("message"));
				if (!Response.IsEmpty())
				{
					// Must be called on Game Thread
					AsyncTask(ENamedThreads::GameThread, [this, Response]()
					{
						AddMessage(TEXT("Agent"), Response, false);
					});
				}
			}
		});

		WebSocket->OnConnected.AddLambda([this]()
		{
			AsyncTask(ENamedThreads::GameThread, [this]()
			{
				SetConnectionStatus(true);
				AddMessage(TEXT("System"), TEXT("Connected to Wwise AI Agent."), false);
			});
		});

		WebSocket->OnDisconnected.AddLambda([this](const FString& Reason)
		{
			AsyncTask(ENamedThreads::GameThread, [this]()
			{
				SetConnectionStatus(false);
				AddMessage(TEXT("System"), TEXT("Disconnected from Wwise AI Agent."), false);
			});
		});
	}

	ChildSlot
	[
		SNew(SVerticalBox)

		// --- Top: Connection Status Bar ---
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(4.f)
		[
			SNew(SHorizontalBox)

			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			.Padding(2.f, 0.f)
			[
				SAssignNew(ConnectionStatusIcon, SImage)
				.Image(WAB_GET_BRUSH("Icons.FilledCircle"))
				.ColorAndOpacity(FSlateColor(FLinearColor::Red))
				.DesiredSizeOverride(FVector2D(10.f, 10.f))
			]

			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			.Padding(4.f, 0.f)
			[
				SAssignNew(ConnectionStatusText, STextBlock)
				.Text(FText::FromString(TEXT("Disconnected")))
				.Font(WAB_GET_FONT_STYLE("SmallFont"))
				.ColorAndOpacity(FSlateColor(FLinearColor(0.7f, 0.7f, 0.7f)))
			]

			+ SHorizontalBox::Slot()
			.FillWidth(1.f)
			[
				SNew(SSpacer)
			]

			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			.Padding(2.f, 0.f)
			[
				SNew(STextBlock)
				.Text(FText::FromString(TEXT("Wwise AI Agent")))
				.Font(WAB_GET_FONT_STYLE("BoldFont"))
			]
		]

		// --- Middle: Chat Message Area ---
		+ SVerticalBox::Slot()
		.FillHeight(1.f)
		.Padding(4.f)
		[
			SNew(SBorder)
			.BorderImage(WAB_GET_BRUSH("ToolPanel.DarkGroupBorder"))
			.Padding(4.f)
			[
				SAssignNew(MessageScrollBox, SScrollBox)
				+ SScrollBox::Slot()
				[
					SNew(SVerticalBox)
					// Messages will be added dynamically
				]
			]
		]

		// --- Bottom: Input Area ---
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(4.f)
		[
			SNew(SHorizontalBox)

			+ SHorizontalBox::Slot()
			.FillWidth(1.f)
			.Padding(0.f, 0.f, 4.f, 0.f)
			[
				SAssignNew(InputTextBox, SEditableTextBox)
				.HintText(FText::FromString(TEXT("Type a message to the Wwise AI Agent...")))
				.OnTextCommitted(FOnTextCommitted::CreateSP(this, &SWwiseAgentChatPanel::OnInputTextCommitted))
			]

			+ SHorizontalBox::Slot()
			.AutoWidth()
			[
				SNew(SButton)
				.Text(FText::FromString(TEXT("Send")))
				.OnClicked(FOnClicked::CreateSP(this, &SWwiseAgentChatPanel::OnSendClicked))
				.IsEnabled_Lambda([this]() -> bool { return bIsConnected; })
			]
		]
	];

	// Add welcome message
	AddMessage(TEXT("System"), TEXT("Welcome to Wwise AI Agent. Waiting for connection..."), false);
}

// ============================================================================
// Public API
// ============================================================================

void SWwiseAgentChatPanel::AddMessage(const FString& Sender, const FString& Message, bool bIsUser)
{
	if (!MessageScrollBox.IsValid()) return;

	TSharedRef<SWidget> MessageWidget = BuildMessageWidget(Sender, Message, bIsUser);

	MessageScrollBox->AddSlot()
	.Padding(2.f, 4.f)
	[
		MessageWidget
	];

	// Auto-scroll to bottom
	MessageScrollBox->ScrollToEnd();
}

void SWwiseAgentChatPanel::ClearMessages()
{
	if (MessageScrollBox.IsValid())
	{
		MessageScrollBox->ClearChildren();
	}
}

void SWwiseAgentChatPanel::SetConnectionStatus(bool bConnected)
{
	bIsConnected = bConnected;

	if (ConnectionStatusIcon.IsValid())
	{
		ConnectionStatusIcon->SetColorAndOpacity(
			FSlateColor(bConnected ? FLinearColor::Green : FLinearColor::Red));
	}

	if (ConnectionStatusText.IsValid())
	{
		ConnectionStatusText->SetText(
			FText::FromString(bConnected ? TEXT("Connected") : TEXT("Disconnected")));
	}
}

// ============================================================================
// Private Handlers
// ============================================================================

FReply SWwiseAgentChatPanel::OnSendClicked()
{
	SendCurrentInput();
	return FReply::Handled();
}

void SWwiseAgentChatPanel::OnInputTextCommitted(const FText& Text, ETextCommit::Type CommitType)
{
	if (CommitType == ETextCommit::OnEnter)
	{
		SendCurrentInput();
	}
}

void SWwiseAgentChatPanel::SendCurrentInput()
{
	if (!InputTextBox.IsValid()) return;

	FString UserText = InputTextBox->GetText().ToString().TrimStartAndEnd();
	if (UserText.IsEmpty()) return;

	// Display user message
	AddMessage(TEXT("You"), UserText, true);

	// Send to Agent
	if (WebSocket.IsValid() && WebSocket->IsConnected())
	{
		WebSocket->SendChatMessage(UserText);
	}
	else
	{
		AddMessage(TEXT("System"), TEXT("Not connected to Agent. Message not sent."), false);
	}

	// Clear input
	InputTextBox->SetText(FText::GetEmpty());
}

TSharedRef<SWidget> SWwiseAgentChatPanel::BuildMessageWidget(
	const FString& Sender, const FString& Message, bool bIsUser)
{
	FLinearColor BgColor = bIsUser
		? FLinearColor(0.15f, 0.25f, 0.4f, 1.0f)   // Blue-ish for user
		: (Sender == TEXT("System")
			? FLinearColor(0.2f, 0.2f, 0.2f, 1.0f)  // Dark grey for system
			: FLinearColor(0.1f, 0.3f, 0.15f, 1.0f)); // Green-ish for agent

	FLinearColor TextColor = FLinearColor::White;
	FLinearColor SenderColor = bIsUser
		? FLinearColor(0.6f, 0.8f, 1.0f)
		: FLinearColor(0.5f, 1.0f, 0.6f);

	return SNew(SBorder)
		.BorderImage(WAB_GET_BRUSH("ToolPanel.GroupBorder"))
		.BorderBackgroundColor(FSlateColor(BgColor))
		.Padding(FMargin(8.f, 4.f))
		[
			SNew(SVerticalBox)

			+ SVerticalBox::Slot()
			.AutoHeight()
			[
				SNew(STextBlock)
				.Text(FText::FromString(Sender))
				.Font(WAB_GET_FONT_STYLE("SmallBoldFont"))
				.ColorAndOpacity(FSlateColor(SenderColor))
			]

			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(0.f, 2.f, 0.f, 0.f)
			[
				SNew(STextBlock)
				.Text(FText::FromString(Message))
				.AutoWrapText(true)
				.Font(WAB_GET_FONT_STYLE("SmallFont"))
				.ColorAndOpacity(FSlateColor(TextColor))
			]
		];
}
