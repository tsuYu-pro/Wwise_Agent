# -*- coding: utf-8 -*-
"""
Wwise Agent - AI Client
OpenAI-compatible API client with Function Calling, streaming, and web search.
"""

import os
import sys
import json
import ssl
import time
import re
from typing import List, Dict, Optional, Any, Callable, Generator, Tuple
from urllib.parse import quote_plus

from shared.common_utils import load_config, save_config

# 强制使用本地 lib 目录中的依赖库
_lib_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'lib')
if os.path.exists(_lib_path):
    if _lib_path in sys.path:
        sys.path.remove(_lib_path)
    sys.path.insert(0, _lib_path)

# 导入 requests
HAS_REQUESTS = False
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    pass


# ============================================================
# 联网搜索功能
# ============================================================

class WebSearcher:
    """联网搜索工具 - 多引擎自动降级（Brave → DuckDuckGo）+ 缓存"""
    
    BRAVE_URL = "https://search.brave.com/search"
    DUCKDUCKGO_URL = "https://html.duckduckgo.com/html/"

    _HEADERS = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/120.0.0.0 Safari/537.36'
        ),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept-Encoding': 'gzip, deflate',
    }

    _search_cache: Dict[str, tuple] = {}
    _CACHE_TTL = 300
    _page_cache: Dict[str, tuple] = {}
    _PAGE_CACHE_TTL = 600
    _HAS_TRAFILATURA = False
    
    def __init__(self):
        if not WebSearcher._HAS_TRAFILATURA:
            try:
                import trafilatura  # noqa: F401
                WebSearcher._HAS_TRAFILATURA = True
            except ImportError:
                pass

    @staticmethod
    def _fix_encoding(response) -> str:
        """智能检测并修正 HTTP 响应的编码，避免中文乱码。"""
        ct_enc = response.encoding
        if ct_enc and ct_enc.lower() not in ('iso-8859-1', 'latin-1', 'ascii'):
            return response.text
        raw = response.content[:8192]
        meta_match = re.search(
            rb'<meta[^>]*charset=["\']?\s*([a-zA-Z0-9_-]+)',
            raw, re.IGNORECASE,
        )
        if meta_match:
            declared = meta_match.group(1).decode('ascii', errors='ignore').strip()
            try:
                response.encoding = declared
                return response.text
            except (LookupError, UnicodeDecodeError):
                pass
        apparent = getattr(response, 'apparent_encoding', None)
        if apparent:
            try:
                response.encoding = apparent
                return response.text
            except (LookupError, UnicodeDecodeError):
                pass
        response.encoding = 'utf-8'
        return response.text

    @staticmethod
    def _decode_entities(text: str) -> str:
        """解码 HTML 实体"""
        import html as _html
        try:
            return _html.unescape(text)
        except Exception:
            return text

    def search(self, query: str, max_results: int = 5, timeout: int = 10) -> Dict[str, Any]:
        """执行网络搜索（缓存 + 多引擎自动降级）"""
        cache_key = f"{query}|{max_results}"
        cached = self._search_cache.get(cache_key)
        if cached:
            ts, cached_result = cached
            if (time.time() - ts) < self._CACHE_TTL:
                cached_result = dict(cached_result)
                cached_result['source'] = cached_result.get('source', '') + '(cached)'
                return cached_result

        errors = []
        result = self._search_brave(query, max_results, timeout)
        if result.get('success') and result.get('results'):
            self._search_cache[cache_key] = (time.time(), result)
            return result
        errors.append(f"Brave: {result.get('error', 'no results')}")
        
        result = self._search_duckduckgo(query, max_results, timeout)
        if result.get('success') and result.get('results'):
            self._search_cache[cache_key] = (time.time(), result)
            return result
        errors.append(f"DDG: {result.get('error', 'no results')}")
        
        return {"success": False, "error": f"All engines failed: {'; '.join(errors)}", "results": []}

    def _search_brave(self, query: str, max_results: int, timeout: int) -> Dict[str, Any]:
        if not HAS_REQUESTS:
            return {"success": False, "error": "requests not installed", "results": []}
        try:
            params = {'q': query, 'source': 'web'}
            response = requests.get(
                self.BRAVE_URL, params=params, headers=self._HEADERS, timeout=timeout,
            )
            response.raise_for_status()
            page_html = self._fix_encoding(response)
            results = self._parse_brave_html(page_html, max_results)
            if results:
                return {"success": True, "query": query, "results": results, "source": "Brave"}
            return {"success": False, "error": "Brave returned page but no results parsed", "results": []}
        except Exception as e:
            return {"success": False, "error": str(e), "results": []}

    def _parse_brave_html(self, page_html: str, max_results: int) -> List[Dict[str, str]]:
        results: List[Dict[str, str]] = []
        block_starts = list(re.finditer(
            r'<div[^>]*class="snippet\b[^"]*"[^>]*data-type="web"[^>]*>',
            page_html, re.IGNORECASE,
        ))
        for i, match in enumerate(block_starts[:max_results + 5]):
            start = match.start()
            end = block_starts[i + 1].start() if i + 1 < len(block_starts) else start + 4000
            block = page_html[start:end]
            url_m = re.search(r'<a[^>]*href="(https?://[^"]+)"', block, re.IGNORECASE)
            url = url_m.group(1) if url_m else ''
            if not url or 'brave.com' in url:
                continue
            title = ''
            for title_pat in (
                r'class="title\b[^"]*search-snippet-title[^"]*"[^>]*>(.*?)</div>',
                r'class="[^"]*search-snippet-title[^"]*"[^>]*>(.*?)</(?:span|div)>',
                r'class="snippet-title[^"]*"[^>]*>(.*?)</(?:span|div)>',
            ):
                title_m = re.search(title_pat, block, re.DOTALL | re.IGNORECASE)
                if title_m:
                    title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip()
                    title = re.sub(r'\s*\d{4}年\d{1,2}月\d{1,2}日\s*-?\s*$', '', title)
                    break
            if not title:
                segments = re.findall(r'>([^<]{8,})<', block)
                for seg in segments:
                    seg = seg.strip()
                    if (seg and 'svg' not in seg.lower()
                            and 'path' not in seg.lower()
                            and not seg.startswith('›')
                            and '.' not in seg[:10]):
                        title = self._decode_entities(seg[:120])
                        break
            desc = ''
            for desc_pat in (
                r'class="[^"]*snippet-description[^"]*"[^>]*>(.*?)</(?:div|p|span)>',
                r'class="[^"]*snippet-content[^"]*"[^>]*>(.*?)</(?:div|p|span)>',
            ):
                desc_m = re.search(desc_pat, block, re.DOTALL | re.IGNORECASE)
                if desc_m:
                    desc = re.sub(r'<[^>]+>', '', desc_m.group(1)).strip()
                    desc = self._decode_entities(desc)
                    break
            if not desc:
                segments = re.findall(r'>([^<]{20,})<', block)
                for seg in segments:
                    seg = seg.strip()
                    if (seg and seg != title
                            and 'svg' not in seg.lower()
                            and not seg.startswith('›')
                            and not re.match(r'^[\d年月日\s\-]+$', seg)):
                        desc = self._decode_entities(seg[:300])
                        break
            results.append({
                'title': self._decode_entities(title) if title else '(no title)',
                'url': url,
                'snippet': desc[:300],
            })
            if len(results) >= max_results:
                break
        return results

    def _search_duckduckgo(self, query: str, max_results: int, timeout: int) -> Dict[str, Any]:
        if not HAS_REQUESTS:
            return {"success": False, "error": "requests not installed", "results": []}
        try:
            response = requests.post(
                self.DUCKDUCKGO_URL,
                data={'q': query, 'b': '', 'kl': 'cn-zh'},
                headers=self._HEADERS,
                timeout=timeout,
            )
            response.raise_for_status()
            page_html = self._fix_encoding(response)
            results = self._parse_duckduckgo_html(page_html, max_results)
            if results:
                return {"success": True, "query": query, "results": results, "source": "DuckDuckGo"}
            return {"success": False, "error": "DDG returned page but no results parsed", "results": []}
        except Exception as e:
            return {"success": False, "error": str(e), "results": []}
    
    def _parse_duckduckgo_html(self, page_html: str, max_results: int) -> List[Dict[str, str]]:
        from urllib.parse import unquote, parse_qs, urlparse
        results = []
        pattern = r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>'
        matches = re.findall(pattern, page_html, re.IGNORECASE | re.DOTALL)
        if not matches:
            pattern = r'<a[^>]*rel="nofollow"[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>'
            matches = re.findall(pattern, page_html, re.IGNORECASE | re.DOTALL)
        for url, raw_title in matches[:max_results]:
            if not url or 'duckduckgo.com' in url:
                continue
            title = re.sub(r'<[^>]+>', '', raw_title).strip()
            title = self._decode_entities(title)
            if not title:
                continue
            real_url = url
            if 'uddg=' in url:
                try:
                    parsed = urlparse(url)
                    params = parse_qs(parsed.query)
                    if 'uddg' in params:
                        real_url = unquote(params['uddg'][0])
                except Exception:
                    pass
            results.append({"title": title, "url": real_url, "snippet": ""})
        for pat in (r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
                    r'<td[^>]*class="result-snippet"[^>]*>(.*?)</td>'):
            snippet_matches = re.findall(pat, page_html, re.IGNORECASE | re.DOTALL)
            if snippet_matches:
                for i, raw in enumerate(snippet_matches[:len(results)]):
                    clean = re.sub(r'<[^>]+>', '', raw).strip()
                    clean = self._decode_entities(clean)
                    if clean:
                        results[i]["snippet"] = clean[:300]
                break
        return results

    def fetch_page_content(self, url: str, max_lines: int = 80,
                           start_line: int = 1, timeout: int = 15) -> Dict[str, Any]:
        if not HAS_REQUESTS:
            return {"success": False, "error": "需要安装 requests 库"}
        try:
            cached = self._page_cache.get(url)
            if cached:
                ts, cached_lines = cached
                if (time.time() - ts) < self._PAGE_CACHE_TTL:
                    return self._paginate_lines(url, cached_lines, start_line, max_lines)
            response = requests.get(url, headers=self._HEADERS, timeout=timeout)
            response.raise_for_status()
            page_html = self._fix_encoding(response)
            text = None
            if self._HAS_TRAFILATURA:
                try:
                    import trafilatura
                    text = trafilatura.extract(
                        page_html,
                        include_comments=False,
                        include_tables=True,
                        output_format='txt',
                        favor_recall=True,
                    )
                except Exception:
                    text = None
            if not text:
                text = self._fallback_html_to_text(page_html)
            lines = []
            for line in text.split('\n'):
                cleaned = re.sub(r'[ \t]+', ' ', line).strip()
                if cleaned:
                    lines.append(cleaned)
            self._page_cache[url] = (time.time(), lines)
            if len(self._page_cache) > 50:
                oldest_key = min(self._page_cache, key=lambda k: self._page_cache[k][0])
                del self._page_cache[oldest_key]
            return self._paginate_lines(url, lines, start_line, max_lines)
        except Exception as e:
            return {"success": False, "error": str(e), "url": url}

    def _fallback_html_to_text(self, page_html: str) -> str:
        for tag in ('script', 'style', 'nav', 'footer', 'header', 'aside', 'noscript'):
            page_html = re.sub(
                rf'<{tag}[^>]*>.*?</{tag}>',
                '', page_html, flags=re.DOTALL | re.IGNORECASE,
            )
        page_html = re.sub(r'<br\s*/?\s*>', '\n', page_html, flags=re.IGNORECASE)
        page_html = re.sub(
            r'</(?:p|div|li|tr|td|th|h[1-6]|blockquote|section|article)>',
            '\n', page_html, flags=re.IGNORECASE,
        )
        text = re.sub(r'<[^>]+>', ' ', page_html)
        return self._decode_entities(text)

    @staticmethod
    def _paginate_lines(url: str, lines: List[str], start_line: int, max_lines: int) -> Dict[str, Any]:
        total_lines = len(lines)
        offset = max(0, start_line - 1)
        page_lines = lines[offset:offset + max_lines]
        end_line = offset + len(page_lines)
        if not page_lines:
            return {
                "success": True,
                "url": url,
                "content": f"[已到末尾] 该网页共 {total_lines} 行，start_line={start_line} 超出范围。"
            }
        content = '\n'.join(page_lines)
        if end_line < total_lines:
            next_start = end_line + 1
            content += (
                f"\n\n[分页提示] 当前显示第 {offset+1}-{end_line} 行，共 {total_lines} 行。"
                f"如需后续内容，请调用 fetch_webpage(url=\"{url}\", start_line={next_start})。"
            )
        else:
            content += f"\n\n[全部内容已显示] 第 {offset+1}-{end_line} 行，共 {total_lines} 行。"
        return {"success": True, "url": url, "content": content}


# ============================================================
# Wwise 工具定义（30 个）
# ============================================================

WWISE_TOOLS = [
    # ---- 查询工具 (9) ----
    {
        "type": "function",
        "function": {
            "name": "get_project_hierarchy",
            "description": "获取 Wwise 项目顶层结构概览，包括各 Hierarchy 的子节点数量、Wwise 版本等。首次了解项目时调用。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_object_properties",
            "description": "获取指定 Wwise 对象的属性详情（支持分页）。设置属性前必须先调用此工具确认正确的属性名和类型。",
            "parameters": {
                "type": "object",
                "properties": {
                    "object_path": {
                        "type": "string",
                        "description": "对象路径，如 '\\Actor-Mixer Hierarchy\\Default Work Unit\\MySound'"
                    },
                    "page": {
                        "type": "integer",
                        "description": "页码（从1开始），属性较多时翻页查看"
                    },
                    "page_size": {
                        "type": "integer",
                        "description": "每页属性数量，默认 30"
                    }
                },
                "required": ["object_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_objects",
            "description": "按关键词模糊搜索 Wwise 对象。返回匹配的对象列表（名称、类型、路径）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词"
                    },
                    "type_filter": {
                        "type": "string",
                        "description": "按类型过滤，如 'Sound', 'Event', 'Bus', 'ActorMixer' 等（可选）"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "最大结果数，默认 20"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_bus_topology",
            "description": "获取 Master-Mixer Hierarchy 中所有 Bus 的拓扑结构。用于了解音频路由。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_event_actions",
            "description": "获取指定 Event 下所有 Action 的详情（类型、Target 引用等）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_path": {
                        "type": "string",
                        "description": "Event 路径，如 '\\Events\\Default Work Unit\\Play_Footstep'"
                    }
                },
                "required": ["event_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_soundbank_info",
            "description": "获取 SoundBank 信息。不传参数时返回所有 SoundBank 列表。",
            "parameters": {
                "type": "object",
                "properties": {
                    "soundbank_name": {
                        "type": "string",
                        "description": "SoundBank 名称（可选，不传则列出所有）"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_rtpc_list",
            "description": "获取项目中所有 Game Parameter（RTPC）列表。",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_results": {
                        "type": "integer",
                        "description": "最大结果数，默认 50"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_selected_objects",
            "description": "获取 Wwise Authoring 中当前选中的对象列表。不需要知道路径，直接读取用户选中的内容。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_effect_chain",
            "description": "获取对象或 Bus 的 Effect 插件链（最多 4 个插槽）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "object_path": {
                        "type": "string",
                        "description": "对象或 Bus 路径"
                    }
                },
                "required": ["object_path"]
            }
        }
    },
    # ---- 操作工具 (10) ----
    {
        "type": "function",
        "function": {
            "name": "create_object",
            "description": "在指定父节点下创建 Wwise 对象（Sound、ActorMixer、BlendContainer 等）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "对象名称"},
                    "obj_type": {
                        "type": "string",
                        "description": "对象类型，如 'Sound', 'ActorMixer', 'BlendContainer', 'RandomSequenceContainer', 'SwitchContainer', 'Folder' 等"
                    },
                    "parent_path": {
                        "type": "string",
                        "description": "父节点路径，如 '\\Actor-Mixer Hierarchy\\Default Work Unit'"
                    },
                    "on_conflict": {
                        "type": "string",
                        "enum": ["rename", "fail"],
                        "description": "同名冲突策略，默认 'rename'"
                    },
                    "notes": {"type": "string", "description": "备注（可选）"}
                },
                "required": ["name", "obj_type", "parent_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_property",
            "description": "设置对象的一个或多个属性。设置前请先用 get_object_properties 确认正确的属性名。",
            "parameters": {
                "type": "object",
                "properties": {
                    "object_path": {"type": "string", "description": "对象路径"},
                    "property": {"type": "string", "description": "属性名（单个属性时使用）"},
                    "value": {
                        "type": ["number", "string", "boolean"],
                        "description": "属性值（单个属性时使用）"
                    },
                    "properties": {
                        "type": "object",
                        "description": "批量设置：属性名→值的字典（可替代 property+value）"
                    },
                    "platform": {"type": "string", "description": "目标平台（可选）"}
                },
                "required": ["object_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_event",
            "description": "创建 Wwise Event 及其 Action。自动创建 Event + Action 并设置 Target 引用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_name": {"type": "string", "description": "Event 名称"},
                    "action_type": {
                        "type": "string",
                        "enum": ["Play", "Stop", "Pause", "Resume", "Break", "Mute", "UnMute"],
                        "description": "Action 类型"
                    },
                    "target_path": {
                        "type": "string",
                        "description": "Action 目标对象路径"
                    },
                    "parent_path": {
                        "type": "string",
                        "description": "Event 父路径，默认 '\\Events\\Default Work Unit'"
                    }
                },
                "required": ["event_name", "action_type", "target_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "assign_bus",
            "description": "将对象路由到指定 Bus（设置 OverrideOutput + OutputBus 引用）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "object_path": {"type": "string", "description": "对象路径"},
                    "bus_path": {"type": "string", "description": "目标 Bus 路径"}
                },
                "required": ["object_path", "bus_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_object",
            "description": "删除 Wwise 对象。默认会检查是否被 Action 引用，传 force=true 跳过检查。",
            "parameters": {
                "type": "object",
                "properties": {
                    "object_path": {"type": "string", "description": "要删除的对象路径"},
                    "force": {"type": "boolean", "description": "是否跳过引用检查，默认 false"}
                },
                "required": ["object_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "move_object",
            "description": "将对象移动到新的父节点。",
            "parameters": {
                "type": "object",
                "properties": {
                    "object_path": {"type": "string", "description": "要移动的对象路径"},
                    "new_parent_path": {"type": "string", "description": "新父节点路径"}
                },
                "required": ["object_path", "new_parent_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "preview_event",
            "description": "通过 Wwise Transport API 试听 Event。",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_path": {"type": "string", "description": "Event 路径"},
                    "action": {
                        "type": "string",
                        "enum": ["play", "stop", "pause", "resume"],
                        "description": "操作类型，默认 'play'"
                    }
                },
                "required": ["event_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_rtpc_binding",
            "description": "将 Game Parameter（RTPC）绑定到对象属性，设置驱动曲线。",
            "parameters": {
                "type": "object",
                "properties": {
                    "object_path": {"type": "string", "description": "目标对象路径"},
                    "game_parameter_path": {"type": "string", "description": "Game Parameter 路径"},
                    "property_name": {
                        "type": "string",
                        "description": "要绑定的属性名，默认 'Volume'"
                    },
                    "curve_points": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "x": {"type": "number"},
                                "y": {"type": "number"},
                                "shape": {"type": "string"}
                            }
                        },
                        "description": "曲线控制点列表，每个点含 x, y, shape（如 'Linear'）"
                    },
                    "notes": {"type": "string", "description": "备注（可选）"}
                },
                "required": ["object_path", "game_parameter_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_effect",
            "description": "为对象或 Bus 添加 Effect 插件。可用插件类型：RoomVerb, Delay, Compressor, Expander, PeakLimiter, ParametricEQ, MeterFX, GainFX 等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "object_path": {"type": "string", "description": "目标对象或 Bus 路径"},
                    "effect_name": {"type": "string", "description": "Effect 实例名称"},
                    "effect_plugin": {
                        "type": "string",
                        "description": "插件类型名称（如 'RoomVerb', 'Compressor'）或 classId 数字"
                    },
                    "effect_slot": {
                        "type": "integer",
                        "description": "插槽索引 0~3，默认 0"
                    },
                    "effect_params": {
                        "type": "object",
                        "description": "Effect 参数字典（可选）"
                    }
                },
                "required": ["object_path", "effect_name", "effect_plugin"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "remove_effect",
            "description": "清空对象上的所有 Effect 插槽。",
            "parameters": {
                "type": "object",
                "properties": {
                    "object_path": {"type": "string", "description": "目标对象路径"}
                },
                "required": ["object_path"]
            }
        }
    },
    # ---- 批量操作工具 (4) ----
    {
        "type": "function",
        "function": {
            "name": "batch_create",
            "description": "批量创建多个 Wwise 对象。flat 模式：在同一父节点下创建多个同级对象；tree 模式：一次创建嵌套层级结构。全部操作可一键撤销。",
            "parameters": {
                "type": "object",
                "properties": {
                    "parent_path": {
                        "type": "string",
                        "description": "父节点路径"
                    },
                    "objects": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "type": {"type": "string"},
                                "notes": {"type": "string"},
                                "properties": {"type": "object"},
                                "children": {"type": "array"}
                            },
                            "required": ["name", "type"]
                        },
                        "description": "flat 模式：对象数组，每项含 name, type, notes(可选), properties(可选), children(可选)"
                    },
                    "tree": {
                        "type": "object",
                        "description": "tree 模式：嵌套结构，含 name, type, children(递归), notes(可选)"
                    },
                    "on_conflict": {
                        "type": "string",
                        "enum": ["rename", "fail", "merge", "replace"],
                        "description": "同名冲突策略，默认 rename"
                    }
                },
                "required": ["parent_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "batch_set_property",
            "description": "批量设置多个对象的属性。模式1: targets + properties 统一设置相同属性；模式2: items 数组为不同对象设不同属性；模式3: type_filter 按类型自动筛选目标。支持 Streaming、Volume、Positioning 等所有常用属性。",
            "parameters": {
                "type": "object",
                "properties": {
                    "targets": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "对象路径列表（模式1）"
                    },
                    "properties": {
                        "type": "object",
                        "description": "属性名→值的字典"
                    },
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string"},
                                "properties": {"type": "object"}
                            },
                            "required": ["path", "properties"]
                        },
                        "description": "模式2：每项含 path 和 properties"
                    },
                    "type_filter": {
                        "type": "string",
                        "description": "按类型过滤（如 'Sound'），自动对所有该类型对象设置属性"
                    },
                    "name_filter": {
                        "type": "string",
                        "description": "配合 type_filter，按名称关键词进一步过滤"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "batch_delete",
            "description": "批量删除多个 Wwise 对象。支持路径列表或按类型+名称过滤。默认检查引用关系避免误删。支持 dry_run 试运行预览。",
            "parameters": {
                "type": "object",
                "properties": {
                    "paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要删除的对象路径列表"
                    },
                    "type_filter": {
                        "type": "string",
                        "description": "按类型过滤（如 'Sound'）"
                    },
                    "name_filter": {
                        "type": "string",
                        "description": "名称关键词过滤"
                    },
                    "force": {
                        "type": "boolean",
                        "description": "跳过引用检查强制删除，默认 false"
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "试运行：只预览将删除的对象，不实际执行"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "batch_move",
            "description": "批量移动多个 Wwise 对象到新父节点。模式1: source_paths 全部移到同一 target_parent；模式2: items 数组独立映射。",
            "parameters": {
                "type": "object",
                "properties": {
                    "source_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要移动的对象路径列表"
                    },
                    "target_parent": {
                        "type": "string",
                        "description": "目标父节点路径"
                    },
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "source_path": {"type": "string"},
                                "target_parent": {"type": "string"}
                            },
                            "required": ["source_path", "target_parent"]
                        },
                        "description": "独立映射模式"
                    },
                    "on_conflict": {
                        "type": "string",
                        "enum": ["rename", "fail", "replace"],
                        "description": "同名冲突策略，默认 rename"
                    }
                },
                "required": []
            }
        }
    },
    # ---- 验证工具 (2) ----
    {
        "type": "function",
        "function": {
            "name": "verify_structure",
            "description": "结构完整性验证：检查孤儿 Event、Action 无 Target、Sound 无 Bus 等问题。可指定 scope_path 限制检查范围。",
            "parameters": {
                "type": "object",
                "properties": {
                    "scope_path": {
                        "type": "string",
                        "description": "检查范围路径（可选，不传则检查全局）"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "verify_event_completeness",
            "description": "【任务结束前必调用】验证 Event 完整性：检查 Action 是否有 Target、音频文件是否存在、SoundBank 包含状态。",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_path": {
                        "type": "string",
                        "description": "Event 路径"
                    }
                },
                "required": ["event_path"]
            }
        }
    },
    # ---- 兜底工具 (1) ----
    {
        "type": "function",
        "function": {
            "name": "execute_waapi",
            "description": "直接执行原始 WAAPI 调用（兜底工具）。当其他工具不能满足需求时使用。受黑名单保护。",
            "parameters": {
                "type": "object",
                "properties": {
                    "uri": {
                        "type": "string",
                        "description": "WAAPI URI，如 'ak.wwise.core.object.get'"
                    },
                    "args": {
                        "type": "object",
                        "description": "WAAPI 调用参数"
                    },
                    "opts": {
                        "type": "object",
                        "description": "WAAPI 调用选项（可选）"
                    }
                },
                "required": ["uri"]
            }
        }
    },
    # ---- Skill 元工具 (2) ----
    {
        "type": "function",
        "function": {
            "name": "list_skills",
            "description": "列出所有可用的 Wwise Skill（高级分析 / 批量操作工具）。调用前先查看有哪些可用。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_skill",
            "description": "执行指定的 Wwise Skill。先调用 list_skills 查看可用 skill 及其参数。",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "description": "Skill 名称（从 list_skills 获取）"
                    },
                    "params": {
                        "type": "object",
                        "description": "传给 Skill 的参数字典"
                    }
                },
                "required": ["skill_name"]
            }
        }
    },
    # ---- 共享工具 (4) ----
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "联网搜索任意信息。可搜索 Wwise 文档、WAAPI 参考、音频技术文章等。只要用户的问题涉及你不确定或需要最新数据的信息，都应主动调用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "max_results": {"type": "integer", "description": "最大结果数，默认 5"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_webpage",
            "description": "获取指定 URL 的网页正文内容（按行分页）。首次调用返回第 1 行起的内容；如结果末尾有 [分页提示]，可传入 start_line 获取后续行。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "网页 URL"},
                    "start_line": {
                        "type": "integer",
                        "description": "从第几行开始返回（默认 1），用于翻页"
                    }
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_todo",
            "description": "添加一个任务到 Todo 列表。在开始复杂任务前，先用这个工具列出计划的步骤。",
            "parameters": {
                "type": "object",
                "properties": {
                    "todo_id": {"type": "string", "description": "任务唯一 ID"},
                    "text": {"type": "string", "description": "任务描述"},
                    "status": {
                        "type": "string",
                        "enum": ["pending", "in_progress", "done", "error"],
                        "description": "任务状态，默认 pending"
                    }
                },
                "required": ["todo_id", "text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_todo",
            "description": "更新 Todo 任务状态。每完成一个步骤必须立即调用此工具标记为 done。",
            "parameters": {
                "type": "object",
                "properties": {
                    "todo_id": {"type": "string", "description": "要更新的任务 ID"},
                    "status": {
                        "type": "string",
                        "enum": ["pending", "in_progress", "done", "error"],
                        "description": "新状态"
                    }
                },
                "required": ["todo_id", "status"]
            }
        }
    },
]


# ============================================================
# AI 客户端
# ============================================================

class AIClient:
    """AI 客户端，支持流式传输、Function Calling、联网搜索"""
    
    OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
    DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
    GLM_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    OLLAMA_API_URL = "http://localhost:11434/v1/chat/completions"
    DUOJIE_API_URL = "https://api.duojie.games/v1/chat/completions"
    DUOJIE_ANTHROPIC_API_URL = "https://api.duojie.games/v1/messages"
    WLAI_API_URL = "https://api3.wlai.vip/v1/chat/completions"
    CODEBUDDY_CLI_API_URL = "https://api.codebuddy.pro/v1/chat/completions"
    
    _DUOJIE_ANTHROPIC_MODELS = frozenset({'glm-4.7', 'glm-5'})

    _RE_CLEAN_PATTERNS = [
        re.compile(r'</?tool_call[^>]*>'),
        re.compile(r'<arg_key>([^<]+)</arg_key>\s*<arg_value>([^<]+)</arg_value>'),
        re.compile(r'</?arg_key[^>]*>'),
        re.compile(r'</?arg_value[^>]*>'),
        re.compile(r'</?redacted_reasoning[^>]*>'),
    ]

    def __init__(self, api_key: Optional[str] = None):
        self._api_keys: Dict[str, Optional[str]] = {
            'openai': api_key or self._read_api_key('openai'),
            'deepseek': self._read_api_key('deepseek'),
            'glm': self._read_api_key('glm'),
            'ollama': 'ollama',
            'duojie': self._read_api_key('duojie'),
            'wlai': self._read_api_key('wlai'),
            'codebuddy_cli': self._read_api_key('codebuddy_cli'),
        }
        self._ssl_context = self._create_ssl_context()
        self._web_searcher = WebSearcher()
        self._tool_executor: Optional[Callable[[str, dict], dict]] = None
        self._ollama_base_url = "http://localhost:11434"
        self._max_retries = 3
        self._retry_delay = 1.0
        self._chunk_timeout = 60
        self._http_session = requests.Session()
        self._http_session.headers.update({'Content-Type': 'application/json'})
        import threading
        self._stop_event = threading.Event()
    
    def request_stop(self):
        self._stop_event.set()
    
    def reset_stop(self):
        self._stop_event.clear()
    
    def is_stop_requested(self) -> bool:
        return self._stop_event.is_set()

    def set_tool_executor(self, executor: Callable[..., dict]):
        self._tool_executor = executor

    # 查询型工具 & 操作型工具分类
    _QUERY_TOOLS = frozenset({
        'get_project_hierarchy', 'get_object_properties',
        'search_objects', 'get_bus_topology',
        'get_event_actions', 'get_soundbank_info',
        'get_rtpc_list', 'get_selected_objects', 'get_effect_chain',
        'verify_structure', 'verify_event_completeness',
        'search_local_doc',
        'web_search', 'fetch_webpage',
    })
    _OP_TOOLS = frozenset({
        'create_object', 'set_property', 'create_event',
        'assign_bus', 'delete_object', 'move_object',
        'preview_event', 'set_rtpc_binding', 'add_effect', 'remove_effect',
        'execute_waapi',
        'batch_create', 'batch_set_property', 'batch_delete', 'batch_move',
    })

    @staticmethod
    def _paginate_result(text: str, max_lines: int = 50) -> str:
        if not text:
            return text
        lines = text.split('\n')
        total = len(lines)
        if total <= max_lines:
            return text
        page = '\n'.join(lines[:max_lines])
        return (
            f"{page}\n\n"
            f"[分页提示] 显示第 1-{max_lines} 行，共 {total} 行（已截断）。"
            f"当前信息如已足够请直接使用。"
            f"注意：用相同参数重复调用会得到相同结果。"
            f"如需更多信息请换用更精确的查询条件，或使用 fetch_webpage 获取特定 URL 的完整内容（支持 start_line 翻页）。"
        )

    @staticmethod
    def _ensure_tool_call_ids(tool_calls: list) -> list:
        import uuid
        for tc in tool_calls:
            if not tc.get('id'):
                tc['id'] = f"call_{uuid.uuid4().hex[:24]}"
            if not tc.get('type'):
                tc['type'] = 'function'
            fn = tc.get('function', {})
            if not fn.get('name'):
                fn['name'] = 'unknown'
            if not fn.get('arguments', '').strip():
                fn['arguments'] = '{}'
            tc['function'] = fn
        return tool_calls

    # Wwise 路径正则（反斜杠路径）
    _PATH_RE = re.compile(r'\\[\w\s\-\.\\]+')
    _COUNT_RE = re.compile(r'(?:对象数量|总数|错误数|警告数|count|total)[：:\s]*(\d+)', re.IGNORECASE)

    @classmethod
    def _summarize_tool_content(cls, content: str, max_len: int = 200) -> str:
        if not content or len(content) <= max_len:
            return content
        parts = []
        paths = cls._PATH_RE.findall(content)
        if paths:
            unique_paths = list(dict.fromkeys(paths))[:5]
            parts.append("路径: " + ", ".join(unique_paths))
        counts = cls._COUNT_RE.findall(content)
        if counts:
            parts.append("统计: " + ", ".join(counts[:4]))
        if '错误' in content[:100] or 'error' in content[:100].lower():
            first_line = content.split('\n', 1)[0][:200]
            parts.append(first_line)
        elif not parts:
            first_line = content.split('\n', 1)[0][:150]
            parts.append(first_line)
        summary = " | ".join(parts)
        if len(summary) > max_len:
            summary = summary[:max_len]
        return summary + '...[摘要]'

    @staticmethod
    def _strip_image_content(messages: list, keep_recent_user: int = 0) -> int:
        stripped = 0
        protected_indices: set = set()
        if keep_recent_user > 0:
            count = 0
            for i in range(len(messages) - 1, -1, -1):
                if messages[i].get('role') == 'user':
                    protected_indices.add(i)
                    count += 1
                    if count >= keep_recent_user:
                        break
        for idx, msg in enumerate(messages):
            content = msg.get('content')
            if not isinstance(content, list):
                continue
            if idx in protected_indices:
                continue
            text_parts = []
            has_image = False
            for part in content:
                if isinstance(part, dict):
                    if part.get('type') == 'text':
                        text_parts.append(part.get('text', ''))
                    elif part.get('type') == 'image_url':
                        has_image = True
                        stripped += 1
                elif isinstance(part, str):
                    text_parts.append(part)
            if has_image:
                combined = '\n'.join(t for t in text_parts if t)
                if combined:
                    combined += '\n[图片已移除以节省上下文空间]'
                else:
                    combined = '[图片已移除]'
                msg['content'] = combined
        return stripped

    def _progressive_trim(self, working_messages: list, tool_calls_history: list,
                          trim_level: int = 1, supports_vision: bool = True) -> list:
        if not working_messages:
            return working_messages
        if not supports_vision or trim_level >= 3:
            n_stripped = self._strip_image_content(working_messages, keep_recent_user=0)
        elif trim_level == 2:
            n_stripped = self._strip_image_content(working_messages, keep_recent_user=1)
        else:
            n_stripped = self._strip_image_content(working_messages, keep_recent_user=2)
        if n_stripped > 0:
            print(f"[AI Client] 裁剪: 剥离了 {n_stripped} 张图片")
        sys_msg = working_messages[0] if working_messages[0].get('role') == 'system' else None
        body = working_messages[1:] if sys_msg else working_messages[:]
        if not body:
            return working_messages
        rounds = []
        current_round = []
        for m in body:
            if m.get('role') == 'user' and current_round:
                rounds.append(current_round)
                current_round = []
            current_round.append(m)
        if current_round:
            rounds.append(current_round)
        if trim_level <= 1:
            n_rounds = len(rounds)
            protect_n = max(3, int(n_rounds * 0.7))
            for r_idx, rnd in enumerate(rounds):
                if r_idx >= n_rounds - protect_n:
                    break
                for m in rnd:
                    c = m.get('content') or ''
                    if m.get('role') == 'tool' and isinstance(c, str) and len(c) > 300:
                        m['content'] = self._summarize_tool_content(c, 300)
            keep_rounds = max(5, int(n_rounds * 0.7))
            if n_rounds > keep_rounds:
                rounds = rounds[-keep_rounds:]
        elif trim_level == 2:
            rounds = rounds[-3:] if len(rounds) > 3 else rounds
            for r_idx, rnd in enumerate(rounds):
                if r_idx >= len(rounds) - 2:
                    break
                for m in rnd:
                    c = m.get('content') or ''
                    if m.get('role') == 'tool' and isinstance(c, str) and len(c) > 150:
                        m['content'] = self._summarize_tool_content(c, 150)
        else:
            rounds = rounds[-2:] if len(rounds) > 2 else rounds
            for rnd in rounds[:-1]:
                for m in rnd:
                    c = m.get('content') or ''
                    if m.get('role') == 'tool' and isinstance(c, str) and len(c) > 100:
                        m['content'] = self._summarize_tool_content(c, 100)
        body = [m for rnd in rounds for m in rnd]
        result = ([sys_msg] if sys_msg else []) + body
        history_summary = ""
        if tool_calls_history:
            op_history = [h for h in tool_calls_history if h['tool_name'] not in self._QUERY_TOOLS]
            if op_history:
                recent = op_history[-8:]
                lines = []
                for h in recent:
                    r = h.get('result', {})
                    status = 'ok' if (isinstance(r, dict) and r.get('success')) else 'err'
                    r_str = str(r.get('result', '') if isinstance(r, dict) else r)[:60]
                    lines.append(f"  [{status}] {h['tool_name']}: {r_str}")
                history_summary = "\n已完成的操作:\n" + "\n".join(lines)
        result.append({
            'role': 'system',
            'content': (
                f'[上下文管理] 已自动裁剪历史（级别 {trim_level}）。'
                f'{history_summary}'
                f'\n请继续完成当前任务。不要提及此裁剪。'
            )
        })
        print(f"[AI Client] 渐进式裁剪: level={trim_level}, "
              f"消息 {len(working_messages)} → {len(result)}, "
              f"轮次 {len(rounds)}")
        return result
    
    def _sanitize_working_messages(self, messages: list) -> list:
        valid_tc_ids = set()
        for msg in messages:
            if msg.get('role') == 'assistant' and 'tool_calls' in msg:
                self._ensure_tool_call_ids(msg['tool_calls'])
                for tc in msg['tool_calls']:
                    if tc.get('id'):
                        valid_tc_ids.add(tc['id'])
        sanitized = []
        for msg in messages:
            if msg.get('role') == 'tool':
                tc_id = msg.get('tool_call_id', '')
                if not tc_id or tc_id not in valid_tc_ids:
                    continue
            sanitized.append(msg)
        return sanitized

    # 已自带分页的工具
    _SELF_PAGED_TOOLS = frozenset({
        'get_object_properties',
    })

    def _compress_tool_result(self, tool_name: str, result: dict) -> str:
        if result.get('success'):
            content = result.get('result', '')
            if tool_name in self._SELF_PAGED_TOOLS:
                return content
            if tool_name in self._QUERY_TOOLS:
                return self._paginate_result(content, max_lines=50)
            elif tool_name in self._OP_TOOLS:
                if len(content) > 300:
                    paths = re.findall(r'\\[\w\s\-\.\\]+', content)
                    if paths:
                        content = ' '.join(paths[:5])
                        if len(content) > 300:
                            content = content[:300] + '...'
                    else:
                        content = content[:300]
                return content
            else:
                return self._paginate_result(content, max_lines=80)
        else:
            error = result.get('error', '未知错误')
            return error[:500] if len(error) > 500 else error

    def _create_ssl_context(self):
        try:
            context = ssl.create_default_context()
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            return context
        except Exception as e:
            print(f"[AI Client] ⚠️ SSL 证书验证失败 ({e})，回退到未验证模式。")
            try:
                return ssl._create_unverified_context()
            except Exception:
                return None

    def _read_api_key(self, provider: str) -> Optional[str]:
        provider = (provider or 'openai').lower()
        if provider == 'ollama':
            return 'ollama'
        env_map = {
            'openai': ['OPENAI_API_KEY', 'DCC_AI_OPENAI_API_KEY'],
            'deepseek': ['DEEPSEEK_API_KEY', 'DCC_AI_DEEPSEEK_API_KEY'],
            'glm': ['GLM_API_KEY', 'ZHIPU_API_KEY', 'DCC_AI_GLM_API_KEY'],
            'duojie': ['DUOJIE_API_KEY', 'DCC_AI_DUOJIE_API_KEY'],
            'wlai': ['WLAI_API_KEY', 'DCC_AI_WLAI_API_KEY'],
            'codebuddy_cli': ['CODEBUDDY_CLI_API_KEY', 'DCC_AI_CODEBUDDY_CLI_API_KEY'],
        }
        for env_var in env_map.get(provider, []):
            key = os.environ.get(env_var)
            if key:
                return key
        cfg, _ = load_config('ai', dcc_type='wwise')
        if cfg:
            key_map = {
                'openai': 'openai_api_key', 'deepseek': 'deepseek_api_key',
                'glm': 'glm_api_key', 'duojie': 'duojie_api_key',
                'wlai': 'wlai_api_key', 'codebuddy_cli': 'codebuddy_cli_api_key',
            }
            return cfg.get(key_map.get(provider, '')) or None
        return None

    def has_api_key(self, provider: str = 'openai') -> bool:
        provider = (provider or 'openai').lower()
        if provider == 'ollama':
            return True
        return bool(self._api_keys.get(provider))

    def _get_api_key(self, provider: str) -> Optional[str]:
        return self._api_keys.get((provider or 'openai').lower())

    def set_api_key(self, key: str, persist: bool = False, provider: str = 'openai') -> bool:
        provider = (provider or 'openai').lower()
        key = (key or '').strip()
        if not key:
            return False
        self._api_keys[provider] = key
        if persist:
            cfg, _ = load_config('ai', dcc_type='wwise')
            cfg = cfg or {}
            key_map = {'openai': 'openai_api_key', 'deepseek': 'deepseek_api_key', 'glm': 'glm_api_key'}
            cfg[key_map.get(provider, f'{provider}_api_key')] = key
            ok, _ = save_config('ai', cfg, dcc_type='wwise')
            return ok
        return True

    def get_masked_key(self, provider: str = 'openai') -> str:
        provider = (provider or 'openai').lower()
        if provider == 'ollama':
            return 'Local'
        key = self._get_api_key(provider)
        if not key:
            return ''
        if len(key) <= 10:
            return '*' * len(key)
        return key[:5] + '...' + key[-4:]

    def _is_anthropic_protocol(self, provider: str, model: str) -> bool:
        return provider == 'duojie' and model.lower() in self._DUOJIE_ANTHROPIC_MODELS

    def _get_api_url(self, provider: str, model: str = '') -> str:
        provider = (provider or 'openai').lower()
        if provider == 'deepseek':
            return self.DEEPSEEK_API_URL
        elif provider == 'glm':
            return self.GLM_API_URL
        elif provider == 'ollama':
            return self.OLLAMA_API_URL
        elif provider == 'duojie':
            if model and self._is_anthropic_protocol(provider, model):
                return self.DUOJIE_ANTHROPIC_API_URL
            return self.DUOJIE_API_URL
        elif provider == 'wlai':
            return self.WLAI_API_URL
        elif provider == 'codebuddy_cli':
            return self.CODEBUDDY_CLI_API_URL
        return self.OPENAI_API_URL

    def _get_vendor_name(self, provider: str) -> str:
        names = {
            'openai': 'OpenAI', 'deepseek': 'DeepSeek',
            'glm': 'GLM（智谱AI）', 'ollama': 'Ollama',
            'duojie': '拼好饭', 'wlai': 'WLAI',
            'codebuddy_cli': 'Codebuddy CLI',
        }
        return names.get(provider, provider)
    
    def set_ollama_url(self, base_url: str):
        self._ollama_base_url = base_url.rstrip('/')
        self.OLLAMA_API_URL = f"{self._ollama_base_url}/v1/chat/completions"
    
    def get_ollama_models(self) -> List[str]:
        if not HAS_REQUESTS:
            return ['qwen2.5:14b']
        try:
            response = self._http_session.get(
                f"{self._ollama_base_url}/api/tags", timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                models = [m.get('name', '') for m in data.get('models', [])]
                return models if models else ['qwen2.5:14b']
        except Exception:
            pass
        return ['qwen2.5:14b']

    def test_connection(self, provider: str = 'deepseek') -> Dict[str, Any]:
        provider = (provider or 'deepseek').lower()
        if provider == 'ollama':
            try:
                if HAS_REQUESTS:
                    response = self._http_session.get(
                        f"{self._ollama_base_url}/api/tags", timeout=5
                    )
                    if response.status_code == 200:
                        return {'ok': True, 'url': self._ollama_base_url, 'status': 200}
                    return {'ok': False, 'error': f'Ollama 服务响应异常: {response.status_code}'}
            except Exception as e:
                return {'ok': False, 'error': f'无法连接 Ollama 服务: {str(e)}'}
        api_key = self._get_api_key(provider)
        if not api_key:
            return {'ok': False, 'error': f'缺少 API Key'}
        try:
            if HAS_REQUESTS:
                response = self._http_session.post(
                    self._get_api_url(provider),
                    json={'model': self._get_default_model(provider), 'messages': [{'role': 'user', 'content': 'hi'}], 'max_tokens': 1},
                    headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
                    timeout=15, proxies={'http': None, 'https': None}
                )
                return {'ok': True, 'url': self._get_api_url(provider), 'status': response.status_code}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def _get_default_model(self, provider: str) -> str:
        defaults = {
            'openai': 'gpt-5.2', 'deepseek': 'deepseek-chat',
            'glm': 'glm-4.7', 'ollama': 'qwen2.5:14b',
            'codebuddy_cli': 'gemini-3.0-pro'
        }
        return defaults.get(provider, 'gpt-5.2')

    @staticmethod
    def is_reasoning_model(model: str) -> bool:
        m = model.lower()
        return 'reasoner' in m or 'r1' in m or m == 'glm-4.7'
    
    @staticmethod
    def is_glm47(model: str) -> bool:
        return model.lower() == 'glm-4.7'

    _usage_keys_logged = False

    @staticmethod
    def _parse_usage(usage: dict) -> dict:
        if not usage:
            return {}
        if not AIClient._usage_keys_logged:
            AIClient._usage_keys_logged = True
            print(f"[AI Client] Raw usage keys (首次): {sorted(usage.keys())}")
            for k in ('input_tokens_details', 'prompt_tokens_details', 'completion_tokens_details'):
                v = usage.get(k)
                if v:
                    print(f"[AI Client]   {k}: {v}")
        prompt_tokens = usage.get('prompt_tokens', 0) or usage.get('input_tokens', 0)
        input_details = usage.get('input_tokens_details') or usage.get('prompt_tokens_details') or {}
        if isinstance(input_details, dict):
            cache_hit = (
                input_details.get('cached_tokens')
                or input_details.get('cache_read_input_tokens')
                or input_details.get('cache_read_tokens')
                or 0
            )
        else:
            cache_hit = 0
        if not cache_hit:
            cache_hit = (
                usage.get('prompt_cache_hit_tokens')
                or usage.get('cache_read_input_tokens')
                or usage.get('cache_read_tokens')
                or usage.get('cache_hit_tokens')
                or 0
            )
        cache_write_1h = usage.get('claude_cache_creation_1_h_tokens', 0) or 0
        cache_write_5m = usage.get('claude_cache_creation_5_m_tokens', 0) or 0
        factory_cache_write = cache_write_1h + cache_write_5m
        if isinstance(input_details, dict):
            cache_miss_from_details = (
                input_details.get('cache_creation_input_tokens')
                or input_details.get('cache_creation_tokens')
                or 0
            )
        else:
            cache_miss_from_details = 0
        cache_miss = (
            cache_miss_from_details
            or usage.get('prompt_cache_miss_tokens')
            or usage.get('cache_creation_input_tokens')
            or usage.get('cache_write_tokens')
            or usage.get('cache_miss_tokens')
            or factory_cache_write
            or 0
        )
        completion = usage.get('completion_tokens', 0) or usage.get('output_tokens', 0)
        total = usage.get('total_tokens', 0) or (prompt_tokens + completion)
        reasoning_tokens = 0
        comp_details = usage.get('completion_tokens_details') or {}
        if isinstance(comp_details, dict):
            reasoning_tokens = comp_details.get('reasoning_tokens', 0) or 0
        if not reasoning_tokens:
            reasoning_tokens = usage.get('reasoning_tokens', 0) or 0
        return {
            'prompt_tokens': prompt_tokens,
            'completion_tokens': completion,
            'reasoning_tokens': reasoning_tokens,
            'total_tokens': total,
            'cache_hit_tokens': cache_hit,
            'cache_miss_tokens': cache_miss,
            'cache_hit_rate': (cache_hit / prompt_tokens) if prompt_tokens > 0 else 0,
        }

    # ============================================================
    # Anthropic Messages 协议适配层
    # ============================================================

    @staticmethod
    def _convert_messages_to_anthropic(messages: List[Dict[str, Any]]) -> tuple:
        """将 OpenAI 格式的消息列表转换为 Anthropic Messages API 格式。
        
        Returns:
            (system_text, anthropic_messages)
            - system_text: 系统提示（Anthropic 要求单独传 system 参数）
            - anthropic_messages: Anthropic 格式的 messages 列表
        """
        system_text = ""
        anthropic_msgs: List[Dict[str, Any]] = []
        
        for msg in messages:
            role = msg.get('role', '')
            
            if role == 'system':
                system_text += (("\n\n" if system_text else "") + (msg.get('content', '') or ''))
                continue
            
            if role == 'user':
                content = msg.get('content', '')
                if isinstance(content, list):
                    anth_content = []
                    for part in content:
                        if part.get('type') == 'text':
                            anth_content.append({'type': 'text', 'text': part['text']})
                        elif part.get('type') == 'image_url':
                            url = part.get('image_url', {}).get('url', '')
                            if url.startswith('data:'):
                                import re as _re
                                m = _re.match(r'data:(image/\w+);base64,(.+)', url, _re.DOTALL)
                                if m:
                                    anth_content.append({
                                        'type': 'image',
                                        'source': {
                                            'type': 'base64',
                                            'media_type': m.group(1),
                                            'data': m.group(2),
                                        }
                                    })
                            else:
                                anth_content.append({
                                    'type': 'image',
                                    'source': {'type': 'url', 'url': url}
                                })
                    anthropic_msgs.append({'role': 'user', 'content': anth_content})
                else:
                    anthropic_msgs.append({'role': 'user', 'content': str(content or '')})
                continue
            
            if role == 'assistant':
                content_blocks: List[Dict[str, Any]] = []
                text = msg.get('content')
                if text:
                    content_blocks.append({'type': 'text', 'text': str(text)})
                for tc in (msg.get('tool_calls') or []):
                    func = tc.get('function', {})
                    try:
                        input_obj = json.loads(func.get('arguments', '{}'))
                    except (json.JSONDecodeError, ValueError):
                        input_obj = {}
                    content_blocks.append({
                        'type': 'tool_use',
                        'id': tc.get('id', ''),
                        'name': func.get('name', ''),
                        'input': input_obj,
                    })
                if not content_blocks:
                    content_blocks.append({'type': 'text', 'text': ''})
                anthropic_msgs.append({'role': 'assistant', 'content': content_blocks})
                continue
            
            if role == 'tool':
                tool_result_block = {
                    'type': 'tool_result',
                    'tool_use_id': msg.get('tool_call_id', ''),
                    'content': str(msg.get('content', '')),
                }
                if anthropic_msgs and anthropic_msgs[-1]['role'] == 'user':
                    last_content = anthropic_msgs[-1]['content']
                    if isinstance(last_content, list):
                        last_content.append(tool_result_block)
                    else:
                        anthropic_msgs[-1]['content'] = [
                            {'type': 'text', 'text': last_content},
                            tool_result_block,
                        ]
                else:
                    anthropic_msgs.append({
                        'role': 'user',
                        'content': [tool_result_block],
                    })
                continue
        
        if anthropic_msgs and anthropic_msgs[0]['role'] == 'assistant':
            anthropic_msgs.insert(0, {'role': 'user', 'content': '请继续。'})
        
        merged: List[Dict[str, Any]] = []
        for m in anthropic_msgs:
            if merged and merged[-1]['role'] == m['role']:
                prev_content = merged[-1]['content']
                curr_content = m['content']
                if isinstance(prev_content, str):
                    prev_content = [{'type': 'text', 'text': prev_content}]
                if isinstance(curr_content, str):
                    curr_content = [{'type': 'text', 'text': curr_content}]
                if not isinstance(prev_content, list):
                    prev_content = [prev_content]
                if not isinstance(curr_content, list):
                    curr_content = [curr_content]
                merged[-1]['content'] = prev_content + curr_content
            else:
                merged.append(m)
        
        return system_text, merged

    @staticmethod
    def _convert_tools_to_anthropic(tools: List[dict]) -> List[dict]:
        """将 OpenAI Function Calling 格式的工具列表转换为 Anthropic 格式。"""
        if not tools:
            return []
        anthropic_tools = []
        for tool in tools:
            func = tool.get('function', tool)
            anthropic_tools.append({
                'name': func.get('name', ''),
                'description': func.get('description', ''),
                'input_schema': func.get('parameters', {'type': 'object', 'properties': {}}),
            })
        return anthropic_tools

    def _chat_stream_anthropic(self,
                                messages: List[Dict[str, Any]],
                                model: str,
                                provider: str,
                                temperature: float = 0.17,
                                max_tokens: Optional[int] = None,
                                tools: Optional[List[dict]] = None,
                                tool_choice: str = 'auto',
                                enable_thinking: bool = True,
                                api_key: str = '') -> Generator[Dict[str, Any], None, None]:
        """Anthropic Messages 协议的流式 Chat。"""
        api_url = self._get_api_url(provider, model)
        system_text, anth_messages = self._convert_messages_to_anthropic(messages)
        
        payload: Dict[str, Any] = {
            'model': model,
            'messages': anth_messages,
            'max_tokens': max_tokens or 16384,
            'stream': True,
        }
        if temperature is not None:
            payload['temperature'] = min(max(temperature, 0.0), 1.0)
        if system_text:
            payload['system'] = system_text
        if enable_thinking:
            payload['thinking'] = {'type': 'enabled', 'budget_tokens': min(max_tokens or 16384, 10000)}
        if tools:
            payload['tools'] = self._convert_tools_to_anthropic(tools)
            if tool_choice == 'auto':
                payload['tool_choice'] = {'type': 'auto'}
            elif tool_choice == 'none':
                payload['tool_choice'] = {'type': 'none'}
            elif tool_choice == 'required':
                payload['tool_choice'] = {'type': 'any'}
        
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'text/event-stream',
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
        }
        
        print(f"[AI Client] Anthropic protocol: {api_url} model={model}")
        
        for attempt in range(self._max_retries):
            try:
                with self._http_session.post(
                    api_url, json=payload, headers=headers,
                    stream=True, timeout=(10, self._chunk_timeout),
                    proxies={'http': None, 'https': None}
                ) as response:
                    response.encoding = 'utf-8'
                    print(f"[AI Client] Anthropic response status: {response.status_code}")
                    
                    if response.status_code != 200:
                        try:
                            err = response.json()
                            err_msg = err.get('error', {}).get('message', response.text)
                        except Exception:
                            err_msg = response.text
                        print(f"[AI Client] Anthropic error: {err_msg}")
                        if response.status_code >= 500 and attempt < self._max_retries - 1:
                            wait = self._retry_delay * (attempt + 1)
                            print(f"[AI Client] Anthropic server error {response.status_code}, retrying in {wait}s...")
                            time.sleep(wait)
                            continue
                        yield {"type": "error", "error": f"HTTP {response.status_code}: {err_msg}"}
                        return
                    
                    _content_blocks: Dict[int, Dict[str, Any]] = {}
                    _tool_args_acc: Dict[int, str] = {}
                    _pending_usage: Dict[str, Any] = {}
                    _last_stop_reason = None
                    _got_thinking = False
                    _enable_thinking_flag = enable_thinking
                    
                    import codecs
                    _utf8_decoder = codecs.getincrementaldecoder('utf-8')(errors='ignore')
                    _line_buf = ""
                    _event_type = ""
                    
                    def _process_anthropic_event(event_type: str, data_str: str):
                        nonlocal _content_blocks, _tool_args_acc, _pending_usage, _last_stop_reason, _got_thinking
                        results = []
                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            return results
                        ev_type = data.get('type', event_type)
                        
                        if ev_type == 'message_start':
                            msg = data.get('message', {})
                            usage = msg.get('usage', {})
                            if usage:
                                _pending_usage = self._parse_usage(usage)
                        elif ev_type == 'content_block_start':
                            idx = data.get('index', 0)
                            block = data.get('content_block', {})
                            _content_blocks[idx] = {
                                'type': block.get('type', 'text'),
                                'id': block.get('id', ''),
                                'name': block.get('name', ''),
                            }
                            if block.get('type') == 'tool_use':
                                _tool_args_acc[idx] = ''
                        elif ev_type == 'content_block_delta':
                            idx = data.get('index', 0)
                            delta = data.get('delta', {})
                            delta_type = delta.get('type', '')
                            block_info = _content_blocks.get(idx, {})
                            if delta_type == 'text_delta':
                                text = delta.get('text', '')
                                if text:
                                    results.append({"type": "content", "content": text})
                            elif delta_type == 'thinking_delta':
                                thinking = delta.get('thinking', '')
                                if thinking:
                                    if not _got_thinking:
                                        _got_thinking = True
                                        print(f"[AI Client] 🧠 Anthropic thinking (首个 chunk, len={len(thinking)}, enable={_enable_thinking_flag})")
                                    if _enable_thinking_flag:
                                        results.append({"type": "thinking", "content": thinking})
                            elif delta_type == 'input_json_delta':
                                partial = delta.get('partial_json', '')
                                if partial and idx in _tool_args_acc:
                                    _tool_args_acc[idx] += partial
                                    tool_name = block_info.get('name', '')
                                    if tool_name:
                                        results.append({
                                            "type": "tool_args_delta",
                                            "index": idx,
                                            "name": tool_name,
                                            "delta": partial,
                                            "accumulated": _tool_args_acc[idx],
                                        })
                        elif ev_type == 'content_block_stop':
                            idx = data.get('index', 0)
                            block_info = _content_blocks.get(idx, {})
                            if block_info.get('type') == 'tool_use':
                                tool_id = block_info.get('id', '')
                                tool_name = block_info.get('name', '')
                                args_str = _tool_args_acc.get(idx, '{}')
                                results.append({
                                    "type": "tool_call",
                                    "tool_call": {
                                        'id': tool_id,
                                        'type': 'function',
                                        'function': {
                                            'name': tool_name,
                                            'arguments': args_str,
                                        }
                                    }
                                })
                        elif ev_type == 'message_delta':
                            delta = data.get('delta', {})
                            _last_stop_reason = delta.get('stop_reason')
                            usage = data.get('usage', {})
                            if usage:
                                parsed = self._parse_usage(usage)
                                for k, v in parsed.items():
                                    if isinstance(v, (int, float)):
                                        _pending_usage[k] = _pending_usage.get(k, 0) + v
                        elif ev_type == 'message_stop':
                            finish = 'stop'
                            if _last_stop_reason == 'tool_use':
                                finish = 'tool_calls'
                            elif _last_stop_reason == 'max_tokens':
                                finish = 'length'
                            results.append({
                                "type": "done",
                                "finish_reason": finish,
                                "usage": _pending_usage,
                            })
                        elif ev_type == 'error':
                            err_msg = data.get('error', {}).get('message', str(data))
                            results.append({"type": "error", "error": err_msg})
                        return results
                    
                    _should_return = False
                    for raw_chunk in response.iter_content(chunk_size=4096, decode_unicode=False):
                        if not raw_chunk:
                            continue
                        if self._stop_event.is_set():
                            yield {"type": "stopped", "message": "用户停止了请求"}
                            return
                        decoded = _utf8_decoder.decode(raw_chunk)
                        _line_buf += decoded
                        while '\n' in _line_buf:
                            one_line, _line_buf = _line_buf.split('\n', 1)
                            one_line = one_line.rstrip('\r')
                            if not one_line:
                                continue
                            if one_line.startswith('event: '):
                                _event_type = one_line[7:].strip()
                                continue
                            if one_line.startswith('data: '):
                                data_str = one_line[6:]
                                for item in _process_anthropic_event(_event_type, data_str):
                                    yield item
                                    if item.get('type') in ('done', 'error'):
                                        _should_return = True
                                _event_type = ""
                        if _should_return:
                            return
                    
                    _line_buf += _utf8_decoder.decode(b'', final=True)
                    if _line_buf.strip():
                        for line in _line_buf.strip().split('\n'):
                            line = line.strip()
                            if line.startswith('event: '):
                                _event_type = line[7:].strip()
                            elif line.startswith('data: '):
                                for item in _process_anthropic_event(_event_type, line[6:]):
                                    yield item
                                    if item.get('type') in ('done', 'error'):
                                        return
                    
                    if not _should_return:
                        yield {"type": "done", "finish_reason": _last_stop_reason or "stop", "usage": _pending_usage}
                    return
                    
            except requests.exceptions.Timeout:
                if attempt < self._max_retries - 1:
                    time.sleep(self._retry_delay * (attempt + 1))
                    continue
                yield {"type": "error", "error": f"请求超时（已重试 {self._max_retries} 次）"}
                return
            except requests.exceptions.ConnectionError as e:
                if attempt < self._max_retries - 1:
                    time.sleep(self._retry_delay * (attempt + 1))
                    continue
                yield {"type": "error", "error": f"连接错误: {str(e)}"}
                return
            except Exception as e:
                err_str = str(e)
                is_transient = any(k in err_str for k in (
                    'InvalidChunkLength', 'ChunkedEncodingError',
                    'Connection broken', 'IncompleteRead',
                    'ConnectionReset', 'RemoteDisconnected',
                ))
                if is_transient and attempt < self._max_retries - 1:
                    wait = self._retry_delay * (attempt + 1)
                    print(f"[AI Client] Anthropic 连接中断 ({err_str[:80]}), {wait}s 后重试")
                    time.sleep(wait)
                    continue
                yield {"type": "error", "error": f"请求失败: {err_str}"}
                return

    def _chat_anthropic(self,
                        messages: List[Dict[str, Any]],
                        model: str,
                        provider: str,
                        temperature: float = 0.17,
                        max_tokens: int = 4096,
                        tools: Optional[List[dict]] = None,
                        tool_choice: str = 'auto',
                        api_key: str = '',
                        timeout: int = 60) -> Dict[str, Any]:
        """Anthropic Messages 协议的非流式 Chat。"""
        api_url = self._get_api_url(provider, model)
        system_text, anth_messages = self._convert_messages_to_anthropic(messages)
        
        payload: Dict[str, Any] = {
            'model': model,
            'messages': anth_messages,
            'max_tokens': max_tokens,
        }
        if temperature is not None:
            payload['temperature'] = min(max(temperature, 0.0), 1.0)
        if system_text:
            payload['system'] = system_text
        if tools:
            payload['tools'] = self._convert_tools_to_anthropic(tools)
            if tool_choice == 'auto':
                payload['tool_choice'] = {'type': 'auto'}
        
        headers = {
            'Content-Type': 'application/json',
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
        }
        
        for attempt in range(self._max_retries):
            try:
                response = self._http_session.post(
                    api_url, json=payload, headers=headers,
                    timeout=timeout, proxies={'http': None, 'https': None}
                )
                response.raise_for_status()
                obj = response.json()
                
                content_text = ''
                tool_calls_list = []
                for block in obj.get('content', []):
                    if block.get('type') == 'text':
                        content_text += block.get('text', '')
                    elif block.get('type') == 'tool_use':
                        tool_calls_list.append({
                            'id': block.get('id', ''),
                            'type': 'function',
                            'function': {
                                'name': block.get('name', ''),
                                'arguments': json.dumps(block.get('input', {}), ensure_ascii=False),
                            }
                        })
                
                stop_reason = obj.get('stop_reason', 'end_turn')
                finish = 'stop' if stop_reason == 'end_turn' else ('tool_calls' if stop_reason == 'tool_use' else stop_reason)
                
                return {
                    'ok': True,
                    'content': content_text or None,
                    'tool_calls': tool_calls_list or None,
                    'finish_reason': finish,
                    'usage': self._parse_usage(obj.get('usage', {})),
                    'raw': obj,
                }
            except requests.exceptions.Timeout:
                if attempt < self._max_retries - 1:
                    time.sleep(self._retry_delay)
                    continue
                return {'ok': False, 'error': '请求超时'}
            except Exception as e:
                if attempt < self._max_retries - 1:
                    time.sleep(self._retry_delay)
                    continue
                return {'ok': False, 'error': str(e)}
        
        return {'ok': False, 'error': '请求失败'}

    # ============================================================
    # 流式传输 Chat
    # ============================================================
    
    def chat_stream(self,
                    messages: List[Dict[str, str]],
                    model: str = 'gpt-5.2',
                    provider: str = 'openai',
                    temperature: float = 0.17,
                    max_tokens: Optional[int] = None,
                    tools: Optional[List[dict]] = None,
                    tool_choice: str = 'auto',
                    enable_thinking: bool = True) -> Generator[Dict[str, Any], None, None]:
        """流式 Chat API
        
        Yields:
            {"type": "content", "content": str}
            {"type": "tool_call", "tool_call": dict}
            {"type": "thinking", "content": str}
            {"type": "done", "finish_reason": str}
            {"type": "error", "error": str}
        """
        if not HAS_REQUESTS:
            yield {"type": "error", "error": "需要安装 requests 库"}
            return
        
        provider = (provider or 'openai').lower()
        api_key = self._get_api_key(provider)
        
        if provider != 'ollama' and not api_key:
            yield {"type": "error", "error": f"缺少 {self._get_vendor_name(provider)} API Key"}
            return
        
        # Anthropic 协议分支
        if self._is_anthropic_protocol(provider, model):
            yield from self._chat_stream_anthropic(
                messages=messages, model=model, provider=provider,
                temperature=temperature, max_tokens=max_tokens,
                tools=tools, tool_choice=tool_choice,
                enable_thinking=enable_thinking, api_key=api_key,
            )
            return
        
        api_url = self._get_api_url(provider, model)
        
        payload = {
            'model': model,
            'messages': messages,
            'temperature': temperature,
            'stream': True,
            'stream_options': {'include_usage': True},
        }
        if max_tokens:
            payload['max_tokens'] = max_tokens
        
        if self.is_glm47(model) and provider == 'glm' and enable_thinking:
            payload['thinking'] = {'type': 'enabled'}
            if tools:
                payload['tool_stream'] = True
        
        if tools:
            payload['tools'] = tools
            payload['tool_choice'] = tool_choice
        
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'text/event-stream',
        }
        if provider != 'ollama':
            headers['Authorization'] = f'Bearer {api_key}'
        
        print(f"[AI Client] Requesting {api_url} with model {model}")
        for attempt in range(self._max_retries):
            try:
                with self._http_session.post(
                    api_url, json=payload, headers=headers,
                    stream=True, timeout=(10, self._chunk_timeout),
                    proxies={'http': None, 'https': None}
                ) as response:
                    response.encoding = 'utf-8'
                    print(f"[AI Client] Response status: {response.status_code}")
                    
                    if response.status_code != 200:
                        try:
                            err = response.json()
                            err_msg = err.get('error', {}).get('message', response.text)
                        except:
                            err_msg = response.text
                        print(f"[AI Client] Error: {err_msg}")
                        if response.status_code >= 500 and attempt < self._max_retries - 1:
                            wait = self._retry_delay * (attempt + 1)
                            print(f"[AI Client] Server error {response.status_code}, retrying in {wait}s...")
                            time.sleep(wait)
                            continue
                        yield {"type": "error", "error": f"HTTP {response.status_code}: {err_msg}"}
                        return
                    
                    tool_calls_buffer = {}
                    pending_usage = {}
                    last_finish_reason = None
                    _got_reasoning = False
                    _enable_thinking = enable_thinking
                    
                    import codecs
                    _utf8_decoder = codecs.getincrementaldecoder('utf-8')(errors='ignore')
                    _line_buf = ""
                    
                    def _process_sse_line(line):
                        nonlocal tool_calls_buffer, pending_usage, last_finish_reason, _got_reasoning, _enable_thinking
                        results = []
                        if not line.startswith('data: '):
                            return results
                        data_str = line[6:]
                        if data_str.strip() == '[DONE]':
                            _reason_tokens = pending_usage.get('reasoning_tokens', 0)
                            print(f"[AI Client] Received [DONE], reasoning={'YES' if _got_reasoning else 'NO'}(tokens={_reason_tokens}), usage={pending_usage}")
                            results.append({"type": "done", "finish_reason": last_finish_reason or "stop", "usage": pending_usage})
                            return results
                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            return results
                        choices = data.get('choices', [])
                        usage_data = data.get('usage')
                        if usage_data:
                            pending_usage = self._parse_usage(usage_data)
                        if not choices:
                            return results
                        choice = choices[0]
                        delta = choice.get('delta', {})
                        finish_reason = choice.get('finish_reason')
                        
                        _thinking_text = (
                            delta.get('reasoning_content')
                            or delta.get('thinking_content')
                            or delta.get('reasoning')
                            or ''
                        )
                        if _thinking_text:
                            if not _got_reasoning:
                                _got_reasoning = True
                                _field = ('reasoning_content' if 'reasoning_content' in delta
                                          else 'thinking_content' if 'thinking_content' in delta
                                          else 'reasoning')
                                print(f"[AI Client] 🧠 收到 {_field}（首个 chunk，len={len(_thinking_text)}，enable_thinking={_enable_thinking}）")
                            if _enable_thinking:
                                results.append({"type": "thinking", "content": _thinking_text})
                        
                        if 'content' in delta and delta['content']:
                            results.append({"type": "content", "content": delta['content']})
                        
                        if delta.get('tool_calls'):
                            for tc in delta['tool_calls']:
                                idx = tc.get('index', 0)
                                tc_id = tc.get('id', '')
                                if tc_id and idx in tool_calls_buffer:
                                    existing_id = tool_calls_buffer[idx].get('id', '')
                                    if existing_id and existing_id != tc_id:
                                        idx = max(tool_calls_buffer.keys()) + 1
                                if idx not in tool_calls_buffer:
                                    tool_calls_buffer[idx] = {
                                        'id': tc_id, 'type': 'function',
                                        'function': {'name': '', 'arguments': ''}
                                    }
                                if tc_id:
                                    tool_calls_buffer[idx]['id'] = tc_id
                                if 'function' in tc:
                                    fn = tc['function']
                                    if 'name' in fn and fn['name']:
                                        tool_calls_buffer[idx]['function']['name'] = fn['name']
                                    if 'arguments' in fn:
                                        tool_calls_buffer[idx]['function']['arguments'] += fn['arguments']
                                        _tname = tool_calls_buffer[idx]['function'].get('name', '')
                                        if _tname:
                                            results.append({
                                                "type": "tool_args_delta",
                                                "index": idx, "name": _tname,
                                                "delta": fn['arguments'],
                                                "accumulated": tool_calls_buffer[idx]['function']['arguments'],
                                            })
                        
                        if finish_reason:
                            if tool_calls_buffer:
                                import uuid as _uuid
                                fixed_buffer = {}
                                next_fix_idx = max(tool_calls_buffer.keys()) + 1
                                for idx_k in sorted(tool_calls_buffer.keys()):
                                    tc_entry = tool_calls_buffer[idx_k]
                                    args_str = tc_entry['function']['arguments'].strip()
                                    if args_str.startswith('{'):
                                        try:
                                            json.loads(args_str)
                                            fixed_buffer[idx_k] = tc_entry
                                        except (json.JSONDecodeError, ValueError):
                                            split_parts = []
                                            depth = 0
                                            start = -1
                                            for ci, ch in enumerate(args_str):
                                                if ch == '{':
                                                    if depth == 0:
                                                        start = ci
                                                    depth += 1
                                                elif ch == '}':
                                                    depth -= 1
                                                    if depth == 0 and start >= 0:
                                                        part = args_str[start:ci+1]
                                                        try:
                                                            json.loads(part)
                                                            split_parts.append(part)
                                                        except:
                                                            pass
                                                        start = -1
                                            if split_parts:
                                                print(f"[AI Client] 修复拼接的 tool_call arguments: 拆分为 {len(split_parts)} 个独立调用")
                                                tc_entry['function']['arguments'] = split_parts[0]
                                                fixed_buffer[idx_k] = tc_entry
                                                for extra_args in split_parts[1:]:
                                                    fixed_buffer[next_fix_idx] = {
                                                        'id': f"call_{_uuid.uuid4().hex[:24]}",
                                                        'type': 'function',
                                                        'function': {'name': tc_entry['function']['name'], 'arguments': extra_args}
                                                    }
                                                    next_fix_idx += 1
                                            else:
                                                fixed_buffer[idx_k] = tc_entry
                                    else:
                                        fixed_buffer[idx_k] = tc_entry
                                tool_calls_buffer = fixed_buffer
                                for idx_k in sorted(tool_calls_buffer.keys()):
                                    results.append({"type": "tool_call", "tool_call": tool_calls_buffer[idx_k]})
                                tool_calls_buffer = {}
                            last_finish_reason = finish_reason
                        return results
                    
                    _should_return = False
                    for raw_chunk in response.iter_content(chunk_size=4096, decode_unicode=False):
                        if not raw_chunk:
                            continue
                        if self._stop_event.is_set():
                            yield {"type": "stopped", "message": "用户停止了请求"}
                            return
                        decoded = _utf8_decoder.decode(raw_chunk)
                        _line_buf += decoded
                        while '\n' in _line_buf:
                            one_line, _line_buf = _line_buf.split('\n', 1)
                            one_line = one_line.rstrip('\r')
                            if not one_line:
                                continue
                            for item in _process_sse_line(one_line):
                                yield item
                                if item.get('type') == 'done':
                                    _should_return = True
                        if _should_return:
                            return
                    
                    _line_buf += _utf8_decoder.decode(b'', final=True)
                    if _line_buf.strip():
                        for item in _process_sse_line(_line_buf.strip()):
                            yield item
                            if item.get('type') == 'done':
                                return
                    
                    if tool_calls_buffer:
                        import uuid as _uuid2
                        fixed_buffer2 = {}
                        next_fix_idx2 = max(tool_calls_buffer.keys()) + 1
                        for idx_k2 in sorted(tool_calls_buffer.keys()):
                            tc_entry2 = tool_calls_buffer[idx_k2]
                            args_str2 = tc_entry2['function']['arguments'].strip()
                            if args_str2.startswith('{'):
                                try:
                                    json.loads(args_str2)
                                    fixed_buffer2[idx_k2] = tc_entry2
                                except (json.JSONDecodeError, ValueError):
                                    split_parts2 = []
                                    depth2 = 0
                                    start2 = -1
                                    for ci2, ch2 in enumerate(args_str2):
                                        if ch2 == '{':
                                            if depth2 == 0:
                                                start2 = ci2
                                            depth2 += 1
                                        elif ch2 == '}':
                                            depth2 -= 1
                                            if depth2 == 0 and start2 >= 0:
                                                part2 = args_str2[start2:ci2+1]
                                                try:
                                                    json.loads(part2)
                                                    split_parts2.append(part2)
                                                except:
                                                    pass
                                                start2 = -1
                                    if split_parts2:
                                        print(f"[AI Client] 修复拼接的 tool_call arguments (尾部): 拆分为 {len(split_parts2)} 个独立调用")
                                        tc_entry2['function']['arguments'] = split_parts2[0]
                                        fixed_buffer2[idx_k2] = tc_entry2
                                        for extra_args2 in split_parts2[1:]:
                                            fixed_buffer2[next_fix_idx2] = {
                                                'id': f"call_{_uuid2.uuid4().hex[:24]}",
                                                'type': 'function',
                                                'function': {'name': tc_entry2['function']['name'], 'arguments': extra_args2}
                                            }
                                            next_fix_idx2 += 1
                                    else:
                                        fixed_buffer2[idx_k2] = tc_entry2
                            else:
                                fixed_buffer2[idx_k2] = tc_entry2
                        tool_calls_buffer = fixed_buffer2
                        for idx in sorted(tool_calls_buffer.keys()):
                            yield {"type": "tool_call", "tool_call": tool_calls_buffer[idx]}
                    yield {"type": "done", "finish_reason": last_finish_reason or "stop", "usage": pending_usage}
                    return
                    
            except requests.exceptions.Timeout:
                if attempt < self._max_retries - 1:
                    time.sleep(self._retry_delay * (attempt + 1))
                    continue
                yield {"type": "error", "error": f"请求超时（已重试 {self._max_retries} 次）"}
                return
            except requests.exceptions.ConnectionError as e:
                if attempt < self._max_retries - 1:
                    time.sleep(self._retry_delay * (attempt + 1))
                    continue
                yield {"type": "error", "error": f"连接错误: {str(e)}"}
                return
            except Exception as e:
                err_str = str(e)
                is_transient = any(k in err_str for k in (
                    'InvalidChunkLength', 'ChunkedEncodingError',
                    'Connection broken', 'IncompleteRead',
                    'ConnectionReset', 'RemoteDisconnected',
                ))
                if is_transient and attempt < self._max_retries - 1:
                    wait = self._retry_delay * (attempt + 1)
                    print(f"[AI Client] 连接中断 ({err_str[:80]}), {wait}s 后重试 ({attempt+1}/{self._max_retries})")
                    time.sleep(wait)
                    continue
                yield {"type": "error", "error": f"请求失败: {err_str}"}
                return

    # ============================================================
    # 非流式 Chat（保留兼容性）
    # ============================================================
    
    def chat(self,
             messages: List[Dict[str, str]],
             model: str = 'gpt-5.2',
             provider: str = 'openai',
             temperature: float = 0.17,
             max_tokens: Optional[int] = None,
             timeout: int = 60,
             tools: Optional[List[dict]] = None,
             tool_choice: str = 'auto') -> Dict[str, Any]:
        """非流式 Chat（兼容旧接口）"""
        if not HAS_REQUESTS:
            return {'ok': False, 'error': '需要安装 requests 库'}
        
        provider = (provider or 'openai').lower()
        api_key = self._get_api_key(provider)
        if not api_key:
            return {'ok': False, 'error': f'缺少 API Key'}
        
        payload = {
            'model': model,
            'messages': messages,
            'temperature': temperature,
        }
        if max_tokens:
            payload['max_tokens'] = max_tokens
        if self.is_glm47(model) and provider == 'glm':
            payload['thinking'] = {'type': 'enabled'}
        if tools:
            payload['tools'] = tools
            payload['tool_choice'] = tool_choice
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}',
        }
        
        if self._is_anthropic_protocol(provider, model):
            return self._chat_anthropic(
                messages=messages, model=model, provider=provider,
                temperature=temperature, max_tokens=max_tokens or 4096,
                tools=tools, tool_choice=tool_choice, api_key=api_key,
                timeout=timeout,
            )
        
        for attempt in range(self._max_retries):
            try:
                response = self._http_session.post(
                    self._get_api_url(provider, model),
                    json=payload, headers=headers,
                    timeout=timeout, proxies={'http': None, 'https': None}
                )
                response.raise_for_status()
                obj = response.json()
                choice = obj.get('choices', [{}])[0]
                message = choice.get('message', {})
                return {
                    'ok': True,
                    'content': message.get('content'),
                    'tool_calls': message.get('tool_calls'),
                    'finish_reason': choice.get('finish_reason'),
                    'usage': self._parse_usage(obj.get('usage', {})),
                    'raw': obj
                }
            except requests.exceptions.Timeout:
                if attempt < self._max_retries - 1:
                    time.sleep(self._retry_delay)
                    continue
                return {'ok': False, 'error': '请求超时'}
            except Exception as e:
                if attempt < self._max_retries - 1:
                    time.sleep(self._retry_delay)
                    continue
                return {'ok': False, 'error': str(e)}
        
        return {'ok': False, 'error': '请求失败'}

    # ============================================================
    # Agent Loop（流式版本）
    # ============================================================
    
    def agent_loop_stream(self,
                          messages: List[Dict[str, Any]],
                          model: str = 'gpt-5.2',
                          provider: str = 'openai',
                          max_iterations: int = 999,
                          temperature: float = 0.17,
                          max_tokens: Optional[int] = None,
                          enable_thinking: bool = True,
                          supports_vision: bool = True,
                          tools_override: Optional[List[dict]] = None,
                          on_content: Optional[Callable[[str], None]] = None,
                          on_thinking: Optional[Callable[[str], None]] = None,
                          on_tool_call: Optional[Callable[[str, dict], None]] = None,
                          on_tool_result: Optional[Callable[[str, dict, dict], None]] = None,
                          on_tool_args_delta: Optional[Callable[[str, str, str], None]] = None,
                          on_iteration_start: Optional[Callable[[int], None]] = None) -> Dict[str, Any]:
        """流式 Agent Loop（Wwise 版本）"""
        if not self._tool_executor:
            return {'ok': False, 'error': '未设置工具执行器', 'content': '', 'tool_calls_history': [], 'iterations': 0}
        
        working_messages = list(messages)
        
        if not supports_vision:
            n_stripped = self._strip_image_content(working_messages, keep_recent_user=0)
            if n_stripped > 0:
                print(f"[AI Client] 非视觉模型 ({model})：已剥离 {n_stripped} 张图片")
        
        initial_msg_count = len(working_messages)
        tool_calls_history = []
        call_records = []
        full_content = ""
        iteration = 0
        
        effective_tools = tools_override if tools_override is not None else WWISE_TOOLS
        
        total_usage = {
            'prompt_tokens': 0, 'completion_tokens': 0,
            'reasoning_tokens': 0, 'total_tokens': 0,
            'cache_hit_tokens': 0, 'cache_miss_tokens': 0,
        }
        
        recent_tool_signatures = []
        max_tool_calls = 999
        total_tool_calls = 0
        consecutive_same_calls = 0
        last_call_signature = None
        server_error_retries = 0
        max_server_retries = 3
        
        _turn_dedup_cache: Dict[str, dict] = {}
        _needs_sanitize = True
        
        while iteration < max_iterations:
            if self._stop_event.is_set():
                return {
                    'ok': False, 'error': '用户停止了请求',
                    'content': full_content, 'final_content': '',
                    'new_messages': working_messages[initial_msg_count:],
                    'tool_calls_history': tool_calls_history,
                    'call_records': call_records,
                    'iterations': iteration, 'stopped': True, 'usage': total_usage
                }
            
            iteration += 1
            _call_start = time.time()
            round_content = ""
            round_thinking = ""
            round_tool_calls = []
            should_retry = False
            should_abort = False
            abort_error = ""
            _round_content_started = False
            
            if _needs_sanitize:
                working_messages = self._sanitize_working_messages(working_messages)
                _needs_sanitize = False
            
            if iteration > 1:
                from collections import Counter
                role_counts = Counter(m.get('role', '?') for m in working_messages)
                summary = ', '.join(f"{r}={c}" for r, c in role_counts.items())
                print(f"[AI Client] iteration={iteration}, messages={len(working_messages)} ({summary})")
            
            if on_iteration_start:
                on_iteration_start(iteration)
            
            for chunk in self.chat_stream(
                messages=working_messages, model=model, provider=provider,
                temperature=temperature, max_tokens=max_tokens,
                tools=effective_tools, tool_choice='auto',
                enable_thinking=enable_thinking
            ):
                if self._stop_event.is_set():
                    return {
                        'ok': False, 'error': '用户停止了请求',
                        'content': full_content + round_content, 'final_content': round_content,
                        'new_messages': working_messages[initial_msg_count:],
                        'tool_calls_history': tool_calls_history,
                        'call_records': call_records,
                        'iterations': iteration, 'stopped': True, 'usage': total_usage
                    }
                
                chunk_type = chunk.get('type')
                
                if chunk_type == 'stopped':
                    return {
                        'ok': False, 'error': '用户停止了请求',
                        'content': full_content + round_content, 'final_content': round_content,
                        'new_messages': working_messages[initial_msg_count:],
                        'tool_calls_history': tool_calls_history,
                        'call_records': call_records,
                        'iterations': iteration, 'stopped': True, 'usage': total_usage
                    }
                
                if chunk_type == 'content':
                    content = chunk.get('content', '')
                    cleaned_chunk = content
                    for _pat in self._RE_CLEAN_PATTERNS:
                        cleaned_chunk = _pat.sub('', cleaned_chunk)
                    if cleaned_chunk and not _round_content_started and full_content:
                        if not full_content.endswith('\n\n'):
                            sep = '\n\n' if not full_content.endswith('\n') else '\n'
                            round_content += sep
                            if on_content:
                                on_content(sep)
                        _round_content_started = True
                    elif cleaned_chunk:
                        _round_content_started = True
                    round_content += cleaned_chunk
                    if on_content and cleaned_chunk:
                        on_content(cleaned_chunk)
                
                elif chunk_type == 'thinking':
                    thinking_text = chunk.get('content', '')
                    round_thinking += thinking_text
                    if on_thinking and thinking_text:
                        on_thinking(thinking_text)
                
                elif chunk_type == 'tool_args_delta':
                    if on_tool_args_delta:
                        on_tool_args_delta(
                            chunk.get('name', ''),
                            chunk.get('delta', ''),
                            chunk.get('accumulated', ''),
                        )
                
                elif chunk_type == 'tool_call':
                    tc = chunk.get('tool_call')
                    print(f"[AI Client] Tool call: {tc.get('function', {}).get('name', 'unknown')}")
                    round_tool_calls.append(tc)
                
                elif chunk_type == 'error':
                    error_msg = chunk.get('error', '')
                    error_lower = error_msg.lower()
                    print(f"[AI Client] Agent loop error at iteration {iteration}: {error_msg}")
                    
                    is_context_exceeded = any(k in error_lower for k in (
                        'context_length_exceeded', 'maximum context length',
                        'max_tokens', 'token limit', 'too many tokens',
                        'request too large', 'payload too large',
                        'context window', 'input too long',
                    )) or ('HTTP 413' in error_msg)
                    
                    is_server_transient = any(k in error_msg for k in (
                        'HTTP 502', 'HTTP 503', 'HTTP 529', 'no available',
                        'InvalidChunkLength', 'ChunkedEncodingError',
                        'Connection broken', 'IncompleteRead',
                        'ConnectionReset', 'RemoteDisconnected',
                        '连接错误', '连接中断',
                    ))
                    
                    is_format_error = ('HTTP 4' in error_msg and not is_context_exceeded and iteration > 1)
                    is_compress_fail = '压缩失败' in error_msg
                    is_recoverable = is_context_exceeded or is_server_transient or is_format_error or is_compress_fail
                    
                    if is_recoverable:
                        server_error_retries += 1
                        if server_error_retries > max_server_retries:
                            print(f"[AI Client] 错误已重试 {max_server_retries} 次，放弃")
                            if on_content:
                                on_content(f"\n[连续出错 {max_server_retries} 次，已停止重试。请稍后再试。]\n")
                            should_abort = True
                            abort_error = f"连续出错 {max_server_retries} 次: {error_msg}"
                            break
                        
                        cleanup_count = 0
                        if is_context_exceeded:
                            print(f"[AI Client] 上下文超限，进行渐进式裁剪 (第{server_error_retries}次)")
                            if on_content:
                                on_content(f"\n[上下文超限，正在智能裁剪后重试 ({server_error_retries}/{max_server_retries})...]\n")
                            old_len = len(working_messages)
                            working_messages = self._progressive_trim(
                                working_messages, tool_calls_history,
                                trim_level=server_error_retries,
                                supports_vision=supports_vision
                            )
                            cleanup_count = old_len - len(working_messages)
                        elif is_server_transient or is_compress_fail:
                            wait_seconds = 5 * server_error_retries
                            if on_content:
                                on_content(f"\n[服务端暂时不可用，{wait_seconds}秒后重试 ({server_error_retries}/{max_server_retries})...]\n")
                            time.sleep(wait_seconds)
                            if server_error_retries >= 2:
                                print(f"[AI Client] 服务端连续出错，尝试轻度裁剪上下文")
                                old_len = len(working_messages)
                                working_messages = self._progressive_trim(
                                    working_messages, tool_calls_history,
                                    trim_level=server_error_retries - 1,
                                    supports_vision=supports_vision
                                )
                                cleanup_count = old_len - len(working_messages)
                        else:
                            while (working_messages and cleanup_count < 20 and
                                   working_messages[-1].get('role') in ('tool', 'system')
                                   and working_messages[-1] is not messages[0]):
                                working_messages.pop()
                                cleanup_count += 1
                            if working_messages and working_messages[-1].get('role') == 'assistant':
                                working_messages.pop()
                                cleanup_count += 1
                        
                        print(f"[AI Client] 重试 {server_error_retries}/{max_server_retries}, 移除了 {cleanup_count} 条消息")
                        should_retry = True
                        break
                    
                    should_abort = True
                    abort_error = error_msg
                    break
                
                elif chunk_type == 'done':
                    server_error_retries = 0
                    usage = chunk.get('usage', {})
                    if usage:
                        total_usage['prompt_tokens'] += usage.get('prompt_tokens', 0)
                        total_usage['completion_tokens'] += usage.get('completion_tokens', 0)
                        total_usage['reasoning_tokens'] += usage.get('reasoning_tokens', 0)
                        total_usage['total_tokens'] += usage.get('total_tokens', 0)
                        total_usage['cache_hit_tokens'] += usage.get('cache_hit_tokens', 0)
                        total_usage['cache_miss_tokens'] += usage.get('cache_miss_tokens', 0)
                    
                    import datetime as _dt
                    _call_latency = time.time() - _call_start
                    _rec_inp = usage.get('prompt_tokens', 0)
                    _rec_out = usage.get('completion_tokens', 0)
                    _rec_reason = usage.get('reasoning_tokens', 0)
                    _rec_chit = usage.get('cache_hit_tokens', 0)
                    _rec_cmiss = usage.get('cache_miss_tokens', 0)
                    try:
                        from wwise_agent.utils.token_optimizer import calculate_cost as _calc_cost
                        _rec_cost = _calc_cost(model, _rec_inp, _rec_out, _rec_chit, _rec_cmiss, _rec_reason)
                    except Exception:
                        _rec_cost = 0.0
                    call_records.append({
                        'timestamp': _dt.datetime.now().isoformat(),
                        'model': model, 'iteration': iteration,
                        'input_tokens': _rec_inp, 'output_tokens': _rec_out,
                        'reasoning_tokens': _rec_reason,
                        'cache_hit': _rec_chit, 'cache_miss': _rec_cmiss,
                        'total_tokens': usage.get('total_tokens', 0),
                        'latency': round(_call_latency, 2),
                        'has_tool_calls': len(round_tool_calls) > 0,
                        'estimated_cost': _rec_cost,
                    })
                    break
            
            if should_retry:
                full_content += round_content
                continue
            
            if should_abort:
                return {
                    'ok': False, 'error': abort_error,
                    'content': full_content, 'final_content': '',
                    'new_messages': working_messages[initial_msg_count:],
                    'tool_calls_history': tool_calls_history,
                    'call_records': call_records,
                    'iterations': iteration, 'usage': total_usage
                }
            
            if not round_tool_calls:
                full_content += round_content
                prompt_total = total_usage['cache_hit_tokens'] + total_usage['cache_miss_tokens']
                if prompt_total > 0:
                    total_usage['cache_hit_rate'] = total_usage['cache_hit_tokens'] / prompt_total
                else:
                    total_usage['cache_hit_rate'] = 0
                return {
                    'ok': True,
                    'content': full_content,
                    'final_content': round_content,
                    'new_messages': working_messages[initial_msg_count:],
                    'tool_calls_history': tool_calls_history,
                    'call_records': call_records,
                    'iterations': iteration, 'usage': total_usage
                }
            
            self._ensure_tool_call_ids(round_tool_calls)
            
            for _tc in round_tool_calls:
                _args_str = _tc.get('function', {}).get('arguments', '{}')
                try:
                    json.loads(_args_str)
                except (json.JSONDecodeError, ValueError):
                    _depth = 0
                    _start = -1
                    _fixed = None
                    for _ci, _ch in enumerate(_args_str):
                        if _ch == '{':
                            if _depth == 0:
                                _start = _ci
                            _depth += 1
                        elif _ch == '}':
                            _depth -= 1
                            if _depth == 0 and _start >= 0:
                                _candidate = _args_str[_start:_ci+1]
                                try:
                                    json.loads(_candidate)
                                    _fixed = _candidate
                                except:
                                    pass
                                break
                    _tc['function']['arguments'] = _fixed if _fixed else '{}'
                    print(f"[AI Client] 修正了无效的 tool_call arguments -> {_tc['function']['arguments'][:80]}")
            
            assistant_msg = {'role': 'assistant', 'tool_calls': round_tool_calls}
            assistant_msg['content'] = round_content or None
            if self.is_reasoning_model(model) and provider in ('deepseek', 'glm'):
                assistant_msg['reasoning_content'] = round_thinking or ''
            working_messages.append(assistant_msg)
            
            # 执行工具调用（Wwise 全部通过 WebSocket，无需主线程限制）
            parsed_calls = []
            for tool_call in round_tool_calls:
                tool_id = tool_call.get('id', '')
                function = tool_call.get('function', {})
                tool_name = function.get('name', '')
                args_str = function.get('arguments', '{}')
                try:
                    arguments = json.loads(args_str)
                except:
                    arguments = {}
                parsed_calls.append((tool_id, tool_name, arguments, tool_call))

            # Wwise 查询工具去重
            _DEDUP_TOOLS = frozenset({
                'get_project_hierarchy', 'get_object_properties', 'search_objects',
                'get_bus_topology', 'get_event_actions', 'get_soundbank_info',
                'get_rtpc_list', 'get_selected_objects', 'get_effect_chain',
                'verify_structure', 'verify_event_completeness',
                'search_local_doc', 'list_skills',
            })
            
            # Web 工具可并行，Wwise 工具串行（WAAPI WebSocket 非线程安全）
            _ASYNC_TOOL_NAMES = frozenset({'web_search', 'fetch_webpage'})
            
            results_ordered = [None] * len(parsed_calls)
            dedup_flags = [False] * len(parsed_calls)

            for idx, (tid, tname, targs, _tc) in enumerate(parsed_calls):
                dedup_key = f"{tname}:{json.dumps(targs, sort_keys=True)}"
                if tname in _DEDUP_TOOLS and dedup_key in _turn_dedup_cache:
                    results_ordered[idx] = _turn_dedup_cache[dedup_key]
                    dedup_flags[idx] = True
                    print(f"[AI Client] ♻️ 同轮去重命中: {tname}({json.dumps(targs, ensure_ascii=False)[:80]})")

            uncached_async = [(i, pc) for i, pc in enumerate(parsed_calls) 
                             if pc[1] in _ASYNC_TOOL_NAMES and not dedup_flags[i]]
            uncached_wwise = [(i, pc) for i, pc in enumerate(parsed_calls) 
                             if pc[1] not in _ASYNC_TOOL_NAMES and not dedup_flags[i]]

            # 并行执行 web 工具
            if len(uncached_async) > 1:
                import concurrent.futures
                def _exec_async(idx_pc):
                    idx, (tid, tname, targs, _tc) = idx_pc
                    if tname == 'web_search':
                        return idx, self._execute_web_search(targs)
                    elif tname == 'fetch_webpage':
                        return idx, self._execute_fetch_webpage(targs)
                    return idx, self._tool_executor(tname, **targs)
                with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(uncached_async))) as pool:
                    for idx, result in pool.map(_exec_async, uncached_async):
                        results_ordered[idx] = result
            elif len(uncached_async) == 1:
                idx, (tid, tname, targs, _tc) = uncached_async[0]
                if tname == 'web_search':
                    results_ordered[idx] = self._execute_web_search(targs)
                elif tname == 'fetch_webpage':
                    results_ordered[idx] = self._execute_fetch_webpage(targs)
                else:
                    results_ordered[idx] = self._tool_executor(tname, **targs)

            # 串行执行 Wwise 工具
            for idx, (tid, tname, targs, _tc) in uncached_wwise:
                results_ordered[idx] = self._tool_executor(tname, **targs)
            
            # 缓存维护：操作类工具执行后清除相关查询缓存
            _NETWORK_MUTATING_TOOLS = frozenset({
                'create_object', 'delete_object', 'move_object', 'set_property',
                'assign_bus', 'create_event', 'set_rtpc_binding',
                'add_effect', 'remove_effect', 'execute_waapi',
            })
            has_mutation = any(
                pc[1] in _NETWORK_MUTATING_TOOLS 
                for idx_m, pc in enumerate(parsed_calls) 
                if not dedup_flags[idx_m]
            )
            if has_mutation:
                keys_to_remove = [k for k in _turn_dedup_cache 
                                  if k.startswith(('get_project_hierarchy:', 'get_object_properties:', 'search_objects:', 'get_bus_topology:', 'verify_structure:'))]
                for k in keys_to_remove:
                    del _turn_dedup_cache[k]
            
            for idx, (tid, tname, targs, _tc) in enumerate(parsed_calls):
                if not dedup_flags[idx] and tname in _DEDUP_TOOLS and results_ordered[idx]:
                    dedup_key = f"{tname}:{json.dumps(targs, sort_keys=True)}"
                    _turn_dedup_cache[dedup_key] = results_ordered[idx]

            should_break_tool_limit = False
            for i, (tool_id, tool_name, arguments, _tc) in enumerate(parsed_calls):
                result = results_ordered[i]
                total_tool_calls += 1
                call_signature = f"{tool_name}:{json.dumps(arguments, sort_keys=True)}"
                if total_tool_calls > max_tool_calls:
                    print(f"[AI Client] ⚠️ 达到最大工具调用次数限制 ({max_tool_calls})")
                    should_break_tool_limit = True
                    break
                if call_signature == last_call_signature:
                    consecutive_same_calls += 1
                else:
                    consecutive_same_calls = 1
                    last_call_signature = call_signature
                
                if on_tool_call:
                    on_tool_call(tool_name, arguments)
                tool_calls_history.append({
                    'tool_name': tool_name, 'arguments': arguments, 'result': result
                })
                if on_tool_result:
                    on_tool_result(tool_name, arguments, result)
                result_content = self._compress_tool_result(tool_name, result)
                if dedup_flags[i]:
                    result_content = f"[缓存] 本轮已用相同参数调用过此工具，以下是之前的结果（无需再次调用）:\n{result_content}"
                working_messages.append({
                    'role': 'tool', 'tool_call_id': tool_id, 'content': result_content
                })
                _needs_sanitize = True

            if should_break_tool_limit:
                return {
                    'ok': True,
                    'content': full_content + f"\n\n已达到工具调用次数限制({max_tool_calls})，自动停止。",
                    'final_content': f"\n\n已达到工具调用次数限制({max_tool_calls})，自动停止。",
                    'new_messages': working_messages[initial_msg_count:],
                    'tool_calls_history': tool_calls_history,
                    'call_records': call_records,
                    'iterations': iteration, 'usage': total_usage
                }
            
            # 多轮思考引导
            _round_failed = False
            for _ri, (_tid, _tn, _ta, _tc) in enumerate(parsed_calls):
                if not results_ordered[_ri].get('success'):
                    _round_failed = True
                    break
            if working_messages and working_messages[-1].get('role') == 'tool':
                if _round_failed:
                    working_messages[-1]['content'] += (
                        '\n\n[注意：上述工具调用返回了错误，这是工具调用层面的参数或执行错误，'
                        '不是Wwise内部错误。请直接根据错误信息修正参数后重新调用该工具。]'
                    )
                if enable_thinking:
                    working_messages[-1]['content'] += (
                        '\n\n[重要：你的下一条回复必须以 <think> 标签开头。'
                        '在标签内分析以上执行结果和当前进度，'
                        '检查 Todo 列表中哪些步骤已完成（用 update_todo 标记为 done），'
                        '确认下一步计划后再继续执行。不要跳过 <think> 标签。]'
                    )
            
            full_content += round_content
        
        if not full_content.strip() and tool_calls_history:
            print("[AI Client] ⚠️ Stream模式：工具调用完成但无回复内容，强制要求生成总结")
            working_messages.append({
                'role': 'user', 'content': '请生成最终总结，说明已完成的操作和结果。'
            })
            summary_content = ""
            for chunk in self.chat_stream(
                messages=working_messages, model=model, provider=provider,
                temperature=temperature, max_tokens=max_tokens or 500,
                tools=None, tool_choice=None
            ):
                if chunk.get('type') == 'content':
                    content = chunk.get('content', '')
                    summary_content += content
                    if on_content:
                        on_content(content)
                elif chunk.get('type') == 'done':
                    break
            full_content = summary_content if summary_content else full_content
        
        print(f"[AI Client] Reached max iterations ({iteration})")
        prompt_total = total_usage['cache_hit_tokens'] + total_usage['cache_miss_tokens']
        if prompt_total > 0:
            total_usage['cache_hit_rate'] = total_usage['cache_hit_tokens'] / prompt_total
        else:
            total_usage['cache_hit_rate'] = 0
        return {
            'ok': True,
            'content': full_content if full_content.strip() else "(工具调用完成，但未生成回复)",
            'final_content': '',
            'new_messages': working_messages[initial_msg_count:],
            'tool_calls_history': tool_calls_history,
            'call_records': call_records,
            'iterations': iteration, 'usage': total_usage
        }

    def _execute_web_search(self, arguments: dict) -> dict:
        """执行网络搜索"""
        query = arguments.get('query', '')
        max_results = arguments.get('max_results', 5)
        if not query:
            return {"success": False, "error": "缺少搜索关键词"}
        result = self._web_searcher.search(query, max_results)
        if result.get('success'):
            items = result.get('results', [])
            if not items:
                return {"success": True, "result": f"搜索 '{query}' 未找到结果。可尝试换用不同关键词。"}
            lines = [f"搜索 '{query}' 的结果（来源: {result.get('source', 'Unknown')}，共 {len(items)} 条）：\n"]
            for i, item in enumerate(items, 1):
                lines.append(f"{i}. {item.get('title', '无标题')}")
                lines.append(f"   URL: {item.get('url', '')}")
                snippet = item.get('snippet', '')
                if snippet:
                    lines.append(f"   摘要: {snippet[:300]}")
                lines.append("")
            lines.append("提示: 如需查看详细内容，请用 fetch_webpage(url=...) 获取网页正文。引用信息时务必在段落末标注 [来源: 标题](URL)。请勿用相同关键词重复搜索。")
            return {"success": True, "result": "\n".join(lines)}
        else:
            return {"success": False, "error": result.get('error', '搜索失败')}

    def _execute_fetch_webpage(self, arguments: dict) -> dict:
        """获取网页内容（分页返回，支持翻页）"""
        url = arguments.get('url', '')
        start_line = arguments.get('start_line', 1)
        if not url:
            return {"success": False, "error": "缺少 URL"}
        try:
            start_line = max(1, int(start_line))
        except (TypeError, ValueError):
            start_line = 1
        result = self._web_searcher.fetch_page_content(url, max_lines=80, start_line=start_line)
        if result.get('success'):
            content = result.get('content', '')
            return {"success": True, "result": f"网页正文（{url}）：\n\n{content}"}
        else:
            return {"success": False, "error": result.get('error', '获取失败')}

    def agent_loop(self, *args, **kwargs):
        """兼容旧接口"""
        return self.agent_loop_stream(*args, **kwargs)

    # ============================================================
    # JSON 解析模式（用于不支持 Function Calling 的模型）
    # ============================================================
    
    def _supports_function_calling(self, provider: str, model: str) -> bool:
        """检查模型是否支持原生 Function Calling"""
        if provider == 'ollama':
            return False
        return True
    
    def _get_json_mode_system_prompt(self, tools_list: Optional[List[dict]] = None) -> str:
        """获取 JSON 模式的系统提示（Wwise 执行器模式）"""
        tool_descriptions = []
        for tool in (tools_list or WWISE_TOOLS):
            func = tool['function']
            params = func.get('parameters', {}).get('properties', {})
            required = func.get('parameters', {}).get('required', [])
            param_desc = []
            for pname, pinfo in params.items():
                req_mark = "(必填)" if pname in required else "(可选)"
                param_desc.append(f"    - {pname} {req_mark}: {pinfo.get('description', '')}")
            tool_descriptions.append(f"""
**{func['name']}** - {func['description']}
参数:
{chr(10).join(param_desc) if param_desc else '    无'}
""")
        
        return f"""你是Wwise执行器。只执行，不思考，不解释。

严格禁止（违反会浪费token）:
-禁止生成任何思考过程、推理步骤、分析过程
-禁止说明"为什么"、"让我先"、"我需要"
-禁止逐步说明、分步解释
-禁止输出任何非执行性内容

只允许:
-直接调用工具执行操作
-直接给出执行结果(1句以内)
-不输出任何思考内容

Wwise对象路径输出规范:
-回复中提及对象时必须写完整路径(如\\Actor-Mixer Hierarchy\\Default Work Unit\\MySound)
-路径使用反斜杠分隔

工具调用参数规范（最高优先级）:
-调用前必须确认所有(必填)参数都已填写,缺少必填参数会导致调用失败
-object_path必须用完整路径,不能只写对象名
-参数值类型必须正确:string/number/boolean/array,不要混用
-工具返回"缺少参数"错误时,直接修正参数重试
-每次调用都要完整填写所有必填参数

安全操作规则（必须遵守）:
-首次了解项目时调用get_project_hierarchy,已查询过的不要重复调用
-设置属性前必须先用get_object_properties查询正确的属性名和类型
-创建对象后用返回的路径操作,不要猜测路径
-操作Event前先用get_event_actions确认结构

## 工具调用格式

```json
{{"tool": "工具名称", "args": {{"参数名": "参数值"}}}}
```

规则:
1.每次只调用一个工具
2.工具调用在独立JSON代码块中
3.调用后等待结果再继续
4.不解释，直接执行
5.先查询确认再操作
6.调用前检查所有(必填)参数是否已填写

## 可用工具

{chr(10).join(tool_descriptions)}

## 示例

查询项目结构（不解释，直接执行）:
```json
{{"tool": "get_project_hierarchy", "args": {{"path": "\\\\Actor-Mixer Hierarchy"}}}}
```
"""
    
    def _parse_json_tool_calls(self, content: str) -> List[Dict]:
        """从文本内容中解析 JSON 格式的工具调用"""
        import re
        tool_calls = []
        content = re.sub(r'</?tool_call[^>]*>', '', content)
        content = re.sub(r'<arg_key>([^<]+)</arg_key>\s*<arg_value>([^<]+)</arg_value>', r'"\1": "\2"', content)
        json_blocks = re.findall(r'```(?:json)?\s*\n?({[^`]+})\s*\n?```', content, re.DOTALL)
        if not json_blocks:
            json_pattern = r'\{\s*"(?:tool|name)"\s*:\s*"[^"]+"\s*,\s*"(?:args|arguments)"\s*:\s*\{[^}]+\}\s*\}'
            json_blocks = re.findall(json_pattern, content, re.DOTALL)
        for block in json_blocks:
            try:
                block = block.strip()
                block = re.sub(r',\s*}', '}', block)
                block = re.sub(r',\s*]', ']', block)
                data = json.loads(block)
                if 'tool' in data:
                    tool_calls.append({
                        'name': data['tool'],
                        'arguments': data.get('args', data.get('arguments', {}))
                    })
                elif 'name' in data:
                    tool_calls.append({
                        'name': data['name'],
                        'arguments': data.get('arguments', data.get('args', {}))
                    })
            except (json.JSONDecodeError, KeyError) as e:
                print(f"[AI Client] JSON解析失败: {e}, 内容: {block[:100]}")
                continue
        return tool_calls
    
    def agent_loop_json_mode(self,
                              messages: List[Dict[str, Any]],
                              model: str = 'qwen2.5:14b',
                              provider: str = 'ollama',
                              max_iterations: int = 999,
                              temperature: float = 0.17,
                              max_tokens: Optional[int] = None,
                              enable_thinking: bool = True,
                              supports_vision: bool = True,
                              tools_override: Optional[List[dict]] = None,
                              on_content: Optional[Callable[[str], None]] = None,
                              on_thinking: Optional[Callable[[str], None]] = None,
                              on_tool_call: Optional[Callable[[str, dict], None]] = None,
                              on_tool_result: Optional[Callable[[str, dict, dict], None]] = None,
                              on_tool_args_delta: Optional[Callable[[str, str, str], None]] = None,
                              on_iteration_start: Optional[Callable[[int], None]] = None) -> Dict[str, Any]:
        """JSON 模式 Agent Loop（用于不支持 Function Calling 的模型）"""
        if not self._tool_executor:
            return {'ok': False, 'error': '未设置工具执行器', 'content': '', 'tool_calls_history': [], 'iterations': 0}
        
        effective_tools = tools_override if tools_override is not None else WWISE_TOOLS
        json_system_prompt = self._get_json_mode_system_prompt(effective_tools)
        working_messages = []
        
        system_found = False
        for msg in messages:
            if msg.get('role') == 'system' and not system_found:
                working_messages.append({
                    'role': 'system',
                    'content': msg.get('content', '') + '\n\n' + json_system_prompt
                })
                system_found = True
            else:
                working_messages.append(msg)
        if not system_found:
            working_messages.insert(0, {'role': 'system', 'content': json_system_prompt})
        
        if not supports_vision:
            n_stripped = self._strip_image_content(working_messages, keep_recent_user=0)
            if n_stripped > 0:
                print(f"[AI Client] 非视觉模型 ({model})：已剥离 {n_stripped} 张图片")
        
        tool_calls_history = []
        call_records = []
        full_content = ""
        iteration = 0
        self._json_thinking_buffer = ""
        
        total_usage = {
            'prompt_tokens': 0, 'completion_tokens': 0,
            'reasoning_tokens': 0, 'total_tokens': 0,
            'cache_hit_tokens': 0, 'cache_miss_tokens': 0,
        }
        
        max_tool_calls = 999
        total_tool_calls = 0
        consecutive_same_calls = 0
        last_call_signature = None
        server_error_retries = 0
        max_server_retries = 3
        
        while iteration < max_iterations:
            if self._stop_event.is_set():
                return {
                    'ok': False, 'error': '用户停止了请求',
                    'content': full_content, 'tool_calls_history': tool_calls_history,
                    'call_records': call_records,
                    'iterations': iteration, 'stopped': True, 'usage': total_usage
                }
            
            iteration += 1
            _call_start = time.time()
            round_content = ""
            
            if iteration > 1 and len(working_messages) > 20:
                protect_start = max(1, len(working_messages) - 6)
                for i, m in enumerate(working_messages):
                    if i == 0 or i >= protect_start:
                        continue
                    role = m.get('role', '')
                    if role == 'user':
                        continue
                    c = m.get('content') or ''
                    if role == 'tool' and len(c) > 400:
                        m['content'] = self._summarize_tool_content(c, 400)
                    elif role == 'assistant' and len(c) > 600:
                        m['content'] = c[:600] + '...[已截断]'
            
            if on_iteration_start:
                on_iteration_start(iteration)
            
            for chunk in self.chat_stream(
                messages=working_messages, model=model, provider=provider,
                temperature=temperature, max_tokens=max_tokens,
                tools=None, tool_choice=None
            ):
                if self._stop_event.is_set():
                    return {
                        'ok': False, 'error': '用户停止了请求',
                        'content': full_content + round_content,
                        'tool_calls_history': tool_calls_history,
                        'call_records': call_records,
                        'iterations': iteration, 'stopped': True, 'usage': total_usage
                    }
                
                chunk_type = chunk.get('type')
                if chunk_type == 'content':
                    content = chunk.get('content', '')
                    round_content += content
                    if on_content:
                        on_content(content)
                elif chunk_type == 'thinking':
                    thinking_text = chunk.get('content', '')
                    if on_thinking and thinking_text:
                        on_thinking(thinking_text)
                elif chunk_type == 'error':
                    err_msg = chunk.get('error', '')
                    err_lower = err_msg.lower()
                    is_context_exceeded = any(k in err_lower for k in (
                        'context_length_exceeded', 'maximum context length',
                        'max_tokens', 'token limit', 'too many tokens',
                        'request too large', 'payload too large',
                        'context window', 'input too long',
                    )) or ('HTTP 413' in err_msg)
                    is_server_transient = any(k in err_msg for k in (
                        'HTTP 502', 'HTTP 503', 'HTTP 529', '压缩失败', 'no available'
                    ))
                    if is_context_exceeded or is_server_transient:
                        server_error_retries += 1
                        if server_error_retries > max_server_retries:
                            if on_content:
                                on_content(f"\n[连续出错 {max_server_retries} 次，已停止重试。]\n")
                            return {
                                'ok': False, 'error': f"连续出错: {err_msg}",
                                'content': full_content, 'tool_calls_history': tool_calls_history,
                                'call_records': call_records,
                                'iterations': iteration, 'usage': total_usage
                            }
                        if is_context_exceeded:
                            if on_content:
                                on_content(f"\n[上下文超限，智能裁剪后重试 ({server_error_retries}/{max_server_retries})...]\n")
                            working_messages = self._progressive_trim(
                                working_messages, tool_calls_history,
                                trim_level=server_error_retries,
                                supports_vision=supports_vision
                            )
                        else:
                            wait_seconds = 5 * server_error_retries
                            if on_content:
                                on_content(f"\n[服务端暂时不可用，{wait_seconds}秒后重试 ({server_error_retries}/{max_server_retries})...]\n")
                            time.sleep(wait_seconds)
                            if server_error_retries >= 2:
                                working_messages = self._progressive_trim(
                                    working_messages, tool_calls_history,
                                    trim_level=server_error_retries - 1,
                                    supports_vision=supports_vision
                                )
                        break
                    return {
                        'ok': False, 'error': err_msg,
                        'content': full_content, 'tool_calls_history': tool_calls_history,
                        'call_records': call_records,
                        'iterations': iteration, 'usage': total_usage
                    }
                elif chunk_type == 'done':
                    server_error_retries = 0
                    usage = chunk.get('usage', {})
                    if usage:
                        total_usage['prompt_tokens'] += usage.get('prompt_tokens', 0)
                        total_usage['completion_tokens'] += usage.get('completion_tokens', 0)
                        total_usage['reasoning_tokens'] += usage.get('reasoning_tokens', 0)
                        total_usage['total_tokens'] += usage.get('total_tokens', 0)
                        total_usage['cache_hit_tokens'] += usage.get('cache_hit_tokens', 0)
                        total_usage['cache_miss_tokens'] += usage.get('cache_miss_tokens', 0)
                    import datetime as _dt
                    _call_latency = time.time() - _call_start
                    _rec_inp = usage.get('prompt_tokens', 0)
                    _rec_out = usage.get('completion_tokens', 0)
                    _rec_reason = usage.get('reasoning_tokens', 0)
                    _rec_chit = usage.get('cache_hit_tokens', 0)
                    _rec_cmiss = usage.get('cache_miss_tokens', 0)
                    try:
                        from wwise_agent.utils.token_optimizer import calculate_cost as _calc_cost
                        _rec_cost = _calc_cost(model, _rec_inp, _rec_out, _rec_chit, _rec_cmiss, _rec_reason)
                    except Exception:
                        _rec_cost = 0.0
                    call_records.append({
                        'timestamp': _dt.datetime.now().isoformat(),
                        'model': model, 'iteration': iteration,
                        'input_tokens': _rec_inp, 'output_tokens': _rec_out,
                        'reasoning_tokens': _rec_reason,
                        'cache_hit': _rec_chit, 'cache_miss': _rec_cmiss,
                        'total_tokens': usage.get('total_tokens', 0),
                        'latency': round(_call_latency, 2),
                        'has_tool_calls': False, 'estimated_cost': _rec_cost,
                    })
                    break
            
            cleaned_content = round_content
            for _pat in self._RE_CLEAN_PATTERNS:
                cleaned_content = _pat.sub('', cleaned_content)
            cleaned_content = re.sub(r'<[^>]+>', '', cleaned_content)
            
            tool_calls = self._parse_json_tool_calls(cleaned_content)
            
            if not tool_calls:
                if cleaned_content.strip():
                    if cleaned_content.strip() not in full_content:
                        full_content += cleaned_content
                if not cleaned_content.strip() and tool_calls_history:
                    continue
                prompt_total = total_usage['cache_hit_tokens'] + total_usage['cache_miss_tokens']
                if prompt_total > 0:
                    total_usage['cache_hit_rate'] = total_usage['cache_hit_tokens'] / prompt_total
                else:
                    total_usage['cache_hit_rate'] = 0
                return {
                    'ok': True, 'content': full_content,
                    'tool_calls_history': tool_calls_history,
                    'call_records': call_records,
                    'iterations': iteration, 'usage': total_usage
                }
            
            json_assistant_msg = {'role': 'assistant', 'content': cleaned_content}
            if self.is_reasoning_model(model) and provider in ('deepseek', 'glm'):
                json_assistant_msg['reasoning_content'] = ''
            working_messages.append(json_assistant_msg)
            
            # 执行工具调用
            tool_results = []
            _ASYNC_TOOL_NAMES_JSON = frozenset({'web_search', 'fetch_webpage'})
            async_tc = [(i, tc) for i, tc in enumerate(tool_calls) if tc['name'] in _ASYNC_TOOL_NAMES_JSON]
            wwise_tc = [(i, tc) for i, tc in enumerate(tool_calls) if tc['name'] not in _ASYNC_TOOL_NAMES_JSON]
            exec_results = [None] * len(tool_calls)

            if len(async_tc) > 1:
                import concurrent.futures
                def _exec_async_json(idx_tc):
                    idx, tc = idx_tc
                    tname, targs = tc['name'], tc['arguments']
                    if tname == 'web_search':
                        return idx, self._execute_web_search(targs)
                    elif tname == 'fetch_webpage':
                        return idx, self._execute_fetch_webpage(targs)
                    return idx, self._tool_executor(tname, **targs)
                with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(async_tc))) as pool:
                    for idx, res in pool.map(_exec_async_json, async_tc):
                        exec_results[idx] = res
            elif len(async_tc) == 1:
                idx, tc = async_tc[0]
                tname, targs = tc['name'], tc['arguments']
                if tname == 'web_search':
                    exec_results[idx] = self._execute_web_search(targs)
                elif tname == 'fetch_webpage':
                    exec_results[idx] = self._execute_fetch_webpage(targs)
                else:
                    exec_results[idx] = self._tool_executor(tname, **targs)

            for idx, tc in wwise_tc:
                tname, targs = tc['name'], tc['arguments']
                if not self._tool_executor:
                    exec_results[idx] = {"success": False, "error": f"工具执行器未设置，无法执行工具: {tname}"}
                else:
                    try:
                        exec_results[idx] = self._tool_executor(tname, **targs)
                    except Exception as e:
                        import traceback
                        exec_results[idx] = {"success": False, "error": f"工具执行异常: {str(e)}\n{traceback.format_exc()[:200]}"}

            should_break_limit = False
            for i, tc in enumerate(tool_calls):
                tool_name = tc['name']
                arguments = tc['arguments']
                result = exec_results[i]
                total_tool_calls += 1
                call_signature = f"{tool_name}:{json.dumps(arguments, sort_keys=True)}"
                if total_tool_calls > max_tool_calls:
                    print(f"[AI Client] ⚠️ JSON模式：达到最大工具调用次数限制 ({max_tool_calls})")
                    should_break_limit = True
                    break
                if call_signature == last_call_signature:
                    consecutive_same_calls += 1
                else:
                    consecutive_same_calls = 1
                    last_call_signature = call_signature
                if on_tool_call:
                    on_tool_call(tool_name, arguments)
                tool_calls_history.append({
                    'tool_name': tool_name, 'arguments': arguments, 'result': result
                })
                if not result.get('success'):
                    error_detail = result.get('error', '未知错误')
                    print(f"[AI Client] ⚠️ 工具执行失败: {tool_name}")
                    print(f"[AI Client]   错误详情: {error_detail[:200]}")
                if on_tool_result:
                    on_tool_result(tool_name, arguments, result)
                compressed = self._compress_tool_result(tool_name, result)
                if result.get('success'):
                    tool_results.append(f"{tool_name}:{compressed}")
                else:
                    tool_results.append(f"{tool_name}:错误:{compressed}")

            if should_break_limit:
                return {
                    'ok': True,
                    'content': full_content + f"\n\n已达到工具调用次数限制({max_tool_calls})，自动停止。",
                    'tool_calls_history': tool_calls_history,
                    'iterations': iteration
                }
            
            failed_tool_details = []
            for r in tool_results:
                if ':错误:' in r:
                    failed_tool_details.append(r)
            has_failed_tools = len(failed_tool_details) > 0
            has_pending_todos = False
            for tc in tool_calls_history:
                if tc.get('tool_name') == 'add_todo':
                    has_pending_todos = True
                    break
            
            think_hint = '先在<think>标签内分析执行结果和当前进度，再决定下一步。' if enable_thinking else ''
            todo_hint = '已完成的步骤请立即用 update_todo 标记为 done。'
            if has_failed_tools:
                fail_summary = '; '.join(failed_tool_details)
                prompt = ('|'.join(tool_results)
                          + f'|⚠️ 以下工具调用返回了错误（这是工具调用层面的参数/执行错误，不是Wwise内部错误，'
                          + f'请直接根据错误原因修正参数后重试）: {fail_summary}'
                          + f'|{think_hint}{todo_hint}请根据上述错误原因修正后继续完成任务。不要因为失败就提前结束。')
            elif has_pending_todos and iteration < max_iterations - 2:
                prompt = '|'.join(tool_results) + f'|检测到还有未完成的任务，{think_hint}{todo_hint}请继续执行。'
            elif iteration >= max_iterations - 1:
                prompt = '|'.join(tool_results) + f'|{todo_hint}请生成最终总结，说明已完成的操作'
            else:
                prompt = '|'.join(tool_results) + f'|{think_hint}{todo_hint}继续或总结'
            
            working_messages.append({
                'role': 'user',
                'content': f'[TOOL_RESULT]\n{prompt}'
            })
            
            cleaned_round = round_content
            for _pat in self._RE_CLEAN_PATTERNS:
                cleaned_round = _pat.sub('', cleaned_round)
            cleaned_round = re.sub(r'<[^>]+>', '', cleaned_round)
            if cleaned_round.strip():
                if cleaned_round.strip() not in full_content:
                    full_content += cleaned_round
        
        if not full_content.strip() and tool_calls_history:
            print("[AI Client] ⚠️ JSON模式：工具调用完成但无回复内容，强制要求生成总结")
            working_messages.append({
                'role': 'user', 'content': '请生成最终总结，说明已完成的操作和结果。'
            })
            summary_content = ""
            for chunk in self.chat_stream(
                messages=working_messages, model=model, provider=provider,
                temperature=temperature, max_tokens=max_tokens or 500,
                tools=None, tool_choice=None
            ):
                if chunk.get('type') == 'content':
                    content = chunk.get('content', '')
                    summary_content += content
                    if on_content:
                        on_content(content)
                elif chunk.get('type') == 'done':
                    break
            full_content = summary_content if summary_content else full_content
        
        prompt_total = total_usage['cache_hit_tokens'] + total_usage['cache_miss_tokens']
        if prompt_total > 0:
            total_usage['cache_hit_rate'] = total_usage['cache_hit_tokens'] / prompt_total
        else:
            total_usage['cache_hit_rate'] = 0
        return {
            'ok': True,
            'content': full_content if full_content.strip() else "(工具调用完成，但未生成回复)",
            'tool_calls_history': tool_calls_history,
            'call_records': call_records,
            'iterations': iteration, 'usage': total_usage
        }
    
    def agent_loop_auto(self,
                        messages: List[Dict[str, Any]],
                        model: str = 'gpt-5.2',
                        provider: str = 'openai',
                        **kwargs) -> Dict[str, Any]:
        """自动选择合适的 Agent Loop 模式"""
        if self._supports_function_calling(provider, model):
            return self.agent_loop_stream(messages=messages, model=model, provider=provider, **kwargs)
        else:
            return self.agent_loop_json_mode(messages=messages, model=model, provider=provider, **kwargs)


# 兼容旧代码
OpenAIClient = AIClient

