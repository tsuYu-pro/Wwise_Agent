// Copyright Wwise AI Agent Team. All Rights Reserved.
// WwiseAssetSynchronizer.h — Synchronizes Wwise objects to UE assets (AkAudioEvent, etc.)

#pragma once

#include "CoreMinimal.h"
#include "WwiseAgentBridgeCompat.h"
#include "Dom/JsonObject.h"

/**
 * FWwiseAssetSynchronizer
 *
 * Handles the "Asset Loop" — when Agent creates/renames Wwise objects,
 * this class creates or updates corresponding UE assets (UAkAudioEvent, etc.)
 *
 * Supports two modes:
 * 1. With Wwise Integration Plugin: Creates proper AkAudioEvent / AkAudioBank assets
 * 2. Without Wwise Integration: Creates placeholder DataAsset with metadata
 *
 * Compatible: UE4.27 ~ UE5.7
 */
class WWISEAGENTBRIDGE_API FWwiseAssetSynchronizer
{
public:
	FWwiseAssetSynchronizer();
	~FWwiseAssetSynchronizer();

	/** Initialize the synchronizer */
	void Initialize();

	/** Process an asset sync message from the Agent */
	void ProcessSyncMessage(TSharedPtr<FJsonObject> Payload);

	/** Create a UE asset corresponding to a Wwise Event */
	bool CreateEventAsset(const FString& EventName, const FString& WwisePath, const FString& TargetFolder);

	/** Create a UE asset corresponding to a Wwise AuxBus */
	bool CreateAuxBusAsset(const FString& BusName, const FString& WwisePath, const FString& TargetFolder);

	/** Update an existing UE asset when a Wwise object is renamed */
	bool RenameAsset(const FString& OldName, const FString& NewName, const FString& ObjectType);

	/** Delete a UE asset when the corresponding Wwise object is deleted */
	bool DeleteAsset(const FString& ObjectName, const FString& ObjectType);

	/** Set the default target content folder for synced assets */
	void SetDefaultTargetFolder(const FString& InFolder);

	/** Check if the Wwise UE Integration plugin is available */
	static bool IsWwiseIntegrationAvailable();

private:
	/** Internal helper: create a generic DataAsset placeholder */
	bool CreatePlaceholderAsset(const FString& AssetName, const FString& ObjectType, const FString& WwisePath, const FString& TargetFolder);

	/** Internal helper: save a package after asset creation */
	bool SaveAssetPackage(UPackage* Package);

	/** Helper: get the full content path for a given asset */
	FString GetAssetPath(const FString& AssetName, const FString& ObjectType, const FString& TargetFolder) const;

	FString DefaultTargetFolder = TEXT("/Game/WwiseSync");
};
