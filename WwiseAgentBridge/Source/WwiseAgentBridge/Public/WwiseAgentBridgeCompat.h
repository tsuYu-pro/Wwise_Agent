// Copyright Wwise AI Agent Team. All Rights Reserved.
// WwiseAgentBridgeCompat.h — UE4/UE5 Version Compatibility Macros
// All version-specific differences are centralized here.

#pragma once

#include "Runtime/Launch/Resources/Version.h"

// ============================================================================
// Engine Version Detection Macros
// ============================================================================

// UE version check: UE_VERSION_AT_LEAST(5, 1) = true if UE >= 5.1
#ifndef UE_VERSION_AT_LEAST
#define UE_VERSION_AT_LEAST(MajorVersion, MinorVersion) \
	((ENGINE_MAJOR_VERSION > (MajorVersion)) || \
	 (ENGINE_MAJOR_VERSION == (MajorVersion) && ENGINE_MINOR_VERSION >= (MinorVersion)))
#endif

#define WAB_IS_UE4  (ENGINE_MAJOR_VERSION == 4)
#define WAB_IS_UE5  (ENGINE_MAJOR_VERSION >= 5)

// ============================================================================
// Header Includes (version-dependent)
// ============================================================================

// UE5.0+ moved EditorStyleSet into a separate module
#if UE_VERSION_AT_LEAST(5, 0)
	#include "Styling/AppStyle.h"
	#define WAB_GET_APP_STYLE_SET_NAME()    FAppStyle::GetAppStyleSetName()
	#define WAB_GET_BRUSH(BrushName)        FAppStyle::GetBrush(BrushName)
	#define WAB_GET_STYLE_SET()             FAppStyle::Get()
	#define WAB_GET_FONT_STYLE(StyleName)   FAppStyle::GetFontStyle(StyleName)
	#define WAB_GET_COLOR(ColorName)        FAppStyle::GetColor(ColorName)
	#define WAB_GET_WIDGET_STYLE(Type, StyleName)  FAppStyle::GetWidgetStyle<Type>(StyleName)
#else
	#include "EditorStyleSet.h"
	#define WAB_GET_APP_STYLE_SET_NAME()    FEditorStyle::GetStyleSetName()
	#define WAB_GET_BRUSH(BrushName)        FEditorStyle::GetBrush(BrushName)
	#define WAB_GET_STYLE_SET()             FEditorStyle::Get()
	#define WAB_GET_FONT_STYLE(StyleName)   FEditorStyle::GetFontStyle(StyleName)
	#define WAB_GET_COLOR(ColorName)        FEditorStyle::GetColor(StyleName)
	#define WAB_GET_WIDGET_STYLE(Type, StyleName)  FEditorStyle::GetWidgetStyle<Type>(StyleName)
#endif

// ============================================================================
// Slate & UI Macros
// ============================================================================

// UE5.1+ introduced FSlateIcon with StyleSet parameter changes
#if UE_VERSION_AT_LEAST(5, 1)
	#define WAB_SLATE_ICON(StyleSetName, StyleName)  FSlateIcon(StyleSetName, StyleName)
#else
	#define WAB_SLATE_ICON(StyleSetName, StyleName)  FSlateIcon(StyleSetName, StyleName)
#endif

// FSlateApplication::Get() — consistent across versions but wrapped for safety
#define WAB_SLATE_APP()  FSlateApplication::Get()

// ============================================================================
// ToolMenus (UE4.24+ / UE5)
// ============================================================================

// UToolMenus is available since UE4.24, but the API evolved.
// We target UE4.27+ minimum, so UToolMenus is always available.
#include "ToolMenus.h"

// ============================================================================
// Tab Spawner / Dock Tab API
// ============================================================================

// UE5.0+ uses FGlobalTabmanager -> FGlobalTabManager
// UE4 uses FGlobalTabmanager
#if UE_VERSION_AT_LEAST(5, 0)
	#define WAB_GLOBAL_TAB_MANAGER  FGlobalTabmanager::Get()
#else
	#define WAB_GLOBAL_TAB_MANAGER  FGlobalTabmanager::Get()
#endif

// ============================================================================
// FPlatformProcess (consistent but wrapped for clarity)
// ============================================================================

// CreateProc signature is identical across UE4.27~UE5.7
// No macro needed, but we define a helper for pipe handling.

// UE5.2+ added ReadPipeTimeout
#if UE_VERSION_AT_LEAST(5, 2)
	#define WAB_HAS_READ_PIPE_TIMEOUT  1
#else
	#define WAB_HAS_READ_PIPE_TIMEOUT  0
#endif

// ============================================================================
// WebSocket Module
// ============================================================================

// IWebSocket is available since UE4.20. Interface is stable.
// However, UE5.3+ added SetHeader() helper.
#if UE_VERSION_AT_LEAST(5, 3)
	#define WAB_WEBSOCKET_HAS_SET_HEADER  1
#else
	#define WAB_WEBSOCKET_HAS_SET_HEADER  0
#endif

// ============================================================================
// HTTP Module
// ============================================================================

// FHttpModule / IHttpRequest / IHttpResponse API is stable UE4.27~UE5.7.
// UE5.4+ changed IHttpRequest::Create() factory method.
#if UE_VERSION_AT_LEAST(5, 4)
	#define WAB_CREATE_HTTP_REQUEST()  FHttpModule::Get().CreateRequest()
#else
	#define WAB_CREATE_HTTP_REQUEST()  FHttpModule::Get().CreateRequest()
#endif

// ============================================================================
// Asset Tools / Content Browser
// ============================================================================

// UE5.0+ uses UEditorAssetSubsystem; UE4 uses FAssetRegistryModule.
#if UE_VERSION_AT_LEAST(5, 0)
	#define WAB_HAS_EDITOR_ASSET_SUBSYSTEM  1
#else
	#define WAB_HAS_EDITOR_ASSET_SUBSYSTEM  0
#endif

// UE5.1+ : ContentBrowser module renamed
#if UE_VERSION_AT_LEAST(5, 1)
	#define WAB_CONTENT_BROWSER_MODULE_NAME  "ContentBrowserModule"
#else
	#define WAB_CONTENT_BROWSER_MODULE_NAME  "ContentBrowser"
#endif

// ============================================================================
// FText / Localization helpers
// ============================================================================

// UE5.0+ uses FText::FromString more extensively; UE4 compatible
// No difference needed — kept for documentation purposes.

// ============================================================================
// StatusBar (UE5.0+)
// ============================================================================

#if UE_VERSION_AT_LEAST(5, 0)
	#define WAB_HAS_STATUS_BAR  1
#else
	#define WAB_HAS_STATUS_BAR  0
#endif

// ============================================================================
// Deprecation Suppression
// ============================================================================

// UE5.5+ deprecated some older Slate construction patterns
#if UE_VERSION_AT_LEAST(5, 5)
	#define WAB_SUPPRESS_DEPRECATION_START  PRAGMA_DISABLE_DEPRECATION_WARNINGS
	#define WAB_SUPPRESS_DEPRECATION_END    PRAGMA_ENABLE_DEPRECATION_WARNINGS
#else
	#define WAB_SUPPRESS_DEPRECATION_START
	#define WAB_SUPPRESS_DEPRECATION_END
#endif

// ============================================================================
// Logging Category
// ============================================================================

DECLARE_LOG_CATEGORY_EXTERN(LogWwiseAgentBridge, Log, All);
