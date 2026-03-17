// Copyright Wwise AI Agent Team. All Rights Reserved.

#include "WwiseAgentBridgeSettings.h"

UWwiseAgentBridgeSettings::UWwiseAgentBridgeSettings()
{
	CategoryName = TEXT("Plugins");
}

const UWwiseAgentBridgeSettings* UWwiseAgentBridgeSettings::GetSettings()
{
	return GetDefault<UWwiseAgentBridgeSettings>();
}
