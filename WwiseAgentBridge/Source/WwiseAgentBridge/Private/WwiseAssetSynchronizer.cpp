// Copyright Wwise AI Agent Team. All Rights Reserved.

#include "WwiseAssetSynchronizer.h"
#include "WwiseAgentBridgeCompat.h"

#include "AssetRegistry/AssetRegistryModule.h"
#include "UObject/SavePackage.h"
#include "UObject/Package.h"
#include "UObject/UObjectGlobals.h"
#include "Misc/PackageName.h"
#include "Engine/DataAsset.h"

#if UE_VERSION_AT_LEAST(5, 0)
#include "Subsystems/EditorAssetSubsystem.h"
#include "Editor.h"
#endif

// ============================================================================
// Constructor / Destructor
// ============================================================================

FWwiseAssetSynchronizer::FWwiseAssetSynchronizer()
{
}

FWwiseAssetSynchronizer::~FWwiseAssetSynchronizer()
{
}

// ============================================================================
// Public API
// ============================================================================

void FWwiseAssetSynchronizer::Initialize()
{
	UE_LOG(LogWwiseAgentBridge, Log, TEXT("WwiseAssetSynchronizer initialized. Target folder: %s"), *DefaultTargetFolder);
}

void FWwiseAssetSynchronizer::ProcessSyncMessage(TSharedPtr<FJsonObject> Payload)
{
	if (!Payload.IsValid())
	{
		UE_LOG(LogWwiseAgentBridge, Warning, TEXT("AssetSync: Received invalid payload."));
		return;
	}

	FString Action = Payload->GetStringField(TEXT("action"));
	FString ObjectType = Payload->GetStringField(TEXT("object_type"));
	FString ObjectName = Payload->GetStringField(TEXT("object_name"));
	FString WwisePath = Payload->GetStringField(TEXT("wwise_path"));

	UE_LOG(LogWwiseAgentBridge, Log, TEXT("AssetSync: Action=%s, Type=%s, Name=%s"),
		*Action, *ObjectType, *ObjectName);

	if (Action == TEXT("create"))
	{
		if (ObjectType == TEXT("Event"))
		{
			CreateEventAsset(ObjectName, WwisePath, DefaultTargetFolder);
		}
		else if (ObjectType == TEXT("AuxBus"))
		{
			CreateAuxBusAsset(ObjectName, WwisePath, DefaultTargetFolder);
		}
		else
		{
			CreatePlaceholderAsset(ObjectName, ObjectType, WwisePath, DefaultTargetFolder);
		}
	}
	else if (Action == TEXT("rename"))
	{
		FString NewName = Payload->GetStringField(TEXT("new_name"));
		RenameAsset(ObjectName, NewName, ObjectType);
	}
	else if (Action == TEXT("delete"))
	{
		DeleteAsset(ObjectName, ObjectType);
	}
	else
	{
		UE_LOG(LogWwiseAgentBridge, Warning, TEXT("AssetSync: Unknown action '%s'"), *Action);
	}
}

bool FWwiseAssetSynchronizer::CreateEventAsset(
	const FString& EventName, const FString& WwisePath, const FString& TargetFolder)
{
	UE_LOG(LogWwiseAgentBridge, Log, TEXT("Creating UE asset for Wwise Event: %s"), *EventName);

	// If Wwise Integration is available, create a proper AkAudioEvent
	if (IsWwiseIntegrationAvailable())
	{
		// TODO: When AkAudio module is linked, create UAkAudioEvent directly:
		// UAkAudioEvent* NewEvent = NewObject<UAkAudioEvent>(...);
		// NewEvent->SetRequiredGeneration(true);
		UE_LOG(LogWwiseAgentBridge, Log, TEXT("Wwise Integration detected — would create proper AkAudioEvent."));
	}

	// Fallback: Create a placeholder DataAsset with metadata
	return CreatePlaceholderAsset(EventName, TEXT("Event"), WwisePath, TargetFolder);
}

bool FWwiseAssetSynchronizer::CreateAuxBusAsset(
	const FString& BusName, const FString& WwisePath, const FString& TargetFolder)
{
	UE_LOG(LogWwiseAgentBridge, Log, TEXT("Creating UE asset for Wwise AuxBus: %s"), *BusName);

	if (IsWwiseIntegrationAvailable())
	{
		UE_LOG(LogWwiseAgentBridge, Log, TEXT("Wwise Integration detected — would create proper AkAuxBus."));
	}

	return CreatePlaceholderAsset(BusName, TEXT("AuxBus"), WwisePath, TargetFolder);
}

bool FWwiseAssetSynchronizer::RenameAsset(
	const FString& OldName, const FString& NewName, const FString& ObjectType)
{
	FString OldPath = GetAssetPath(OldName, ObjectType, DefaultTargetFolder);
	FString NewPath = GetAssetPath(NewName, ObjectType, DefaultTargetFolder);

	UE_LOG(LogWwiseAgentBridge, Log, TEXT("Renaming asset: %s -> %s"), *OldPath, *NewPath);

#if UE_VERSION_AT_LEAST(5, 0)
	if (GEditor)
	{
		UEditorAssetSubsystem* AssetSubsystem = GEditor->GetEditorSubsystem<UEditorAssetSubsystem>();
		if (AssetSubsystem)
		{
			return AssetSubsystem->RenameAsset(OldPath, NewPath);
		}
	}
#endif

	// UE4 fallback — use AssetRegistry + AssetTools
	// This is a simplified implementation; production code should use IAssetTools::RenameAssets
	UE_LOG(LogWwiseAgentBridge, Warning, TEXT("Asset rename on UE4 — manual implementation needed."));
	return false;
}

bool FWwiseAssetSynchronizer::DeleteAsset(const FString& ObjectName, const FString& ObjectType)
{
	FString AssetPath = GetAssetPath(ObjectName, ObjectType, DefaultTargetFolder);

	UE_LOG(LogWwiseAgentBridge, Log, TEXT("Deleting asset: %s"), *AssetPath);

#if UE_VERSION_AT_LEAST(5, 0)
	if (GEditor)
	{
		UEditorAssetSubsystem* AssetSubsystem = GEditor->GetEditorSubsystem<UEditorAssetSubsystem>();
		if (AssetSubsystem)
		{
			return AssetSubsystem->DeleteAsset(AssetPath);
		}
	}
#endif

	UE_LOG(LogWwiseAgentBridge, Warning, TEXT("Asset delete on UE4 — manual implementation needed."));
	return false;
}

void FWwiseAssetSynchronizer::SetDefaultTargetFolder(const FString& InFolder)
{
	DefaultTargetFolder = InFolder;
}

bool FWwiseAssetSynchronizer::IsWwiseIntegrationAvailable()
{
	// Check if the AkAudio module is loaded (Wwise UE Integration plugin)
	return FModuleManager::Get().IsModuleLoaded("AkAudio");
}

// ============================================================================
// Private Helpers
// ============================================================================

bool FWwiseAssetSynchronizer::CreatePlaceholderAsset(
	const FString& AssetName, const FString& ObjectType, const FString& WwisePath, const FString& TargetFolder)
{
	FString SubFolder = TargetFolder / ObjectType + TEXT("s");
	FString PackagePath = SubFolder / AssetName;

	// Validate package name
	FString CleanPackagePath = PackagePath;
	FText Reason;
	if (!FPackageName::IsValidLongPackageName(CleanPackagePath, false, &Reason))
	{
		// Try to clean it
		CleanPackagePath = FPackageName::ObjectPathToPackageName(CleanPackagePath);
	}

	UE_LOG(LogWwiseAgentBridge, Log, TEXT("Creating placeholder asset at: %s"), *CleanPackagePath);

	UPackage* Package = CreatePackage(
#if UE_VERSION_AT_LEAST(5, 0)
		*CleanPackagePath
#else
		nullptr, *CleanPackagePath
#endif
	);

	if (!Package)
	{
		UE_LOG(LogWwiseAgentBridge, Error, TEXT("Failed to create package: %s"), *CleanPackagePath);
		return false;
	}

	// Create a simple UDataAsset to hold metadata
	UDataAsset* NewAsset = NewObject<UDataAsset>(
		Package, UDataAsset::StaticClass(),
		*AssetName,
		RF_Public | RF_Standalone
	);

	if (!NewAsset)
	{
		UE_LOG(LogWwiseAgentBridge, Error, TEXT("Failed to create DataAsset: %s"), *AssetName);
		return false;
	}

	// Mark the package dirty
	Package->MarkPackageDirty();

	// Notify the asset registry
	FAssetRegistryModule::AssetCreated(NewAsset);

	// Save
	bool bSaved = SaveAssetPackage(Package);

	UE_LOG(LogWwiseAgentBridge, Log, TEXT("Created placeholder asset '%s' (type=%s, saved=%s)"),
		*AssetName, *ObjectType, bSaved ? TEXT("Yes") : TEXT("No"));

	return bSaved;
}

bool FWwiseAssetSynchronizer::SaveAssetPackage(UPackage* Package)
{
	if (!Package) return false;

	FString PackageFileName = FPackageName::LongPackageNameToFilename(
		Package->GetName(), FPackageName::GetAssetPackageExtension());

#if UE_VERSION_AT_LEAST(5, 0)
	FSavePackageArgs SaveArgs;
	SaveArgs.TopLevelFlags = RF_Public | RF_Standalone;
	return UPackage::SavePackage(Package, nullptr, *PackageFileName, SaveArgs);
#else
	return UPackage::SavePackage(Package, nullptr, RF_Public | RF_Standalone, *PackageFileName);
#endif
}

FString FWwiseAssetSynchronizer::GetAssetPath(
	const FString& AssetName, const FString& ObjectType, const FString& TargetFolder) const
{
	return TargetFolder / ObjectType + TEXT("s") / AssetName;
}
