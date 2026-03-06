# -*- coding: utf-8 -*-
"""
Wwise 文档轻量级索引系统

替代全量向量化 RAG，采用 **dict 索引** 实现 O(1) 查找：
  - WAAPI 函数 → 签名+描述  (from waapi_functions.json)
  - Wwise 对象类型 → 属性+描述  (from object_types.json)
  - 知识库 → 分段检索  (from Doc/*.txt)

数据源：项目 Doc/ 目录下的 JSON 索引文件 + *.txt 知识库
"""

import os
import re
import json
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass


# ============================================================
# 数据结构
# ============================================================

@dataclass
class WaapiDoc:
    """WAAPI 函数文档"""
    uri: str                # e.g. "ak.wwise.core.object.get"
    description: str        # 简要描述
    category: str           # 分类, e.g. "core.object", "core.audio"
    args: List[str]         # 参数名列表


@dataclass
class ObjectTypeDoc:
    """Wwise 对象类型文档"""
    type_name: str          # e.g. "Sound", "RandomSequenceContainer"
    description: str        # 简要描述
    properties: List[str]   # 常用属性名


@dataclass
class KnowledgeChunk:
    """知识库文档片段"""
    title: str              # 小节标题
    content: str            # 小节内容 (≤2000 chars)
    source: str             # 来源文件名
    keywords: List[str]     # 关键词列表 (小写)


# ============================================================
# 核心：轻量级文档索引
# ============================================================

class WwiseDocIndex:
    """Wwise 文档轻量级索引

    使用 dict 实现 O(1) 查找，替代全量向量化。
    索引来源：项目 Doc/ 目录下的 JSON + TXT 文件。
    """

    def __init__(self, doc_dir: Optional[str] = None):
        self._project_root = Path(__file__).parent.parent.parent

        # 索引
        self.waapi_index: Dict[str, WaapiDoc] = {}
        self.object_type_index: Dict[str, ObjectTypeDoc] = {}
        self.knowledge_chunks: List[KnowledgeChunk] = []

        # 辅助索引
        self._waapi_categories: Dict[str, List[str]] = {}  # category → [uri_list]
        self._type_aliases: Dict[str, str] = {}             # 别名(小写) → type_name

        # 缓存
        self._cache_dir = self._project_root / "cache" / "doc_index"
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        # 文档目录
        if doc_dir:
            self._doc_dir = Path(doc_dir)
        else:
            self._doc_dir = self._project_root / "Doc"

        self._load_or_build()
        self._load_knowledge_base()

    # ==========================================================
    # 索引加载 / 构建 / 缓存
    # ==========================================================

    def _load_or_build(self):
        """加载或构建索引"""
        cache_file = self._cache_dir / "wwise_doc_index.json"

        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("version") == 1:
                    self._load_from_cache(data)
                    print(f"[DocIndex] 缓存加载: {len(self.waapi_index)} WAAPI, "
                          f"{len(self.object_type_index)} 对象类型")
                    return
            except Exception as e:
                print(f"[DocIndex] 缓存失败: {e}")

        if not self._doc_dir or not self._doc_dir.is_dir():
            print("[DocIndex] 未找到 Doc/ 目录，文档索引为空")
            return

        print(f"[DocIndex] 构建索引: {self._doc_dir} ...")
        self._build_indexes()

        try:
            self._save_to_cache(cache_file)
            print(f"[DocIndex] 已缓存: {len(self.waapi_index)} WAAPI, "
                  f"{len(self.object_type_index)} 对象类型")
        except Exception as e:
            print(f"[DocIndex] 缓存保存失败: {e}")

    def _build_indexes(self):
        """从 JSON 文件构建索引"""
        # WAAPI 函数索引
        waapi_file = self._doc_dir / "waapi_functions.json"
        if waapi_file.exists():
            self._build_waapi_index(waapi_file)

        # 对象类型索引
        types_file = self._doc_dir / "object_types.json"
        if types_file.exists():
            self._build_object_type_index(types_file)

        self._build_aliases()

    def _build_waapi_index(self, json_path: Path):
        """从 waapi_functions.json 构建 WAAPI 索引"""
        count = 0
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            entries = data if isinstance(data, list) else data.get("functions", [])
            for entry in entries:
                uri = entry.get("uri", "") or entry.get("name", "")
                if not uri:
                    continue
                desc = entry.get("description", "")[:300]
                args = entry.get("args", []) or entry.get("parameters", [])
                if isinstance(args, list) and args and isinstance(args[0], dict):
                    args = [a.get("name", "") for a in args]

                # 分类：从 URI 提取 (ak.wwise.core.object.get → core.object)
                parts = uri.split(".")
                if len(parts) >= 4:
                    cat = ".".join(parts[2:-1])
                else:
                    cat = ""

                self.waapi_index[uri] = WaapiDoc(
                    uri=uri,
                    description=desc,
                    category=cat,
                    args=args[:10],
                )
                if cat:
                    self._waapi_categories.setdefault(cat, []).append(uri)
                count += 1
        except Exception as e:
            print(f"[DocIndex] waapi_functions.json 失败: {e}")
        print(f"[DocIndex]   → {count} WAAPI 函数")

    def _build_object_type_index(self, json_path: Path):
        """从 object_types.json 构建对象类型索引"""
        count = 0
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            entries = data if isinstance(data, list) else data.get("types", [])
            for entry in entries:
                name = entry.get("name", "") or entry.get("type", "")
                if not name:
                    continue
                self.object_type_index[name] = ObjectTypeDoc(
                    type_name=name,
                    description=entry.get("description", "")[:300],
                    properties=entry.get("properties", [])[:20],
                )
                count += 1
        except Exception as e:
            print(f"[DocIndex] object_types.json 失败: {e}")
        print(f"[DocIndex]   → {count} 对象类型")

    def _build_aliases(self):
        """构建别名（用于模糊匹配）"""
        self._type_aliases.clear()
        for tname in self.object_type_index:
            self._type_aliases[tname.lower()] = tname
            # 驼峰拆分别名: RandomSequenceContainer → random sequence container
            words = re.findall(r'[A-Z][a-z]+|[a-z]+|[A-Z]+', tname)
            if words:
                self._type_aliases[" ".join(w.lower() for w in words)] = tname

    # ==========================================================
    # 知识库加载（Doc/*.txt 文件）
    # ==========================================================

    def _load_knowledge_base(self):
        """从 Doc/ 目录递归加载 .txt 知识库文件，按 ## 标题分段

        改进:
        1. 递归加载子目录 Doc/**/*.txt
        2. 知识库缓存: 将解析结果序列化到 JSON 缓存
        3. 增量检测: 按文件修改时间判断是否需要重新解析
        """
        if not self._doc_dir or not self._doc_dir.is_dir():
            return

        txt_files = sorted(self._doc_dir.rglob("*.txt"))
        if not txt_files:
            return

        kb_cache_file = self._cache_dir / "knowledge_base_cache.json"

        # 构建文件指纹 {相对路径: mtime}
        file_fingerprints = {}
        for txt_path in txt_files:
            rel = txt_path.relative_to(self._doc_dir)
            file_fingerprints[str(rel)] = txt_path.stat().st_mtime

        # 尝试增量加载缓存
        if kb_cache_file.exists():
            try:
                with open(kb_cache_file, "r", encoding="utf-8") as f:
                    cache_data = json.load(f)
                cached_fingerprints = cache_data.get("fingerprints", {})
                if cached_fingerprints == file_fingerprints:
                    for chunk_data in cache_data.get("chunks", []):
                        self.knowledge_chunks.append(KnowledgeChunk(
                            title=chunk_data["title"],
                            content=chunk_data["content"],
                            source=chunk_data["source"],
                            keywords=chunk_data["keywords"],
                        ))
                    print(f"[DocIndex] 知识库缓存加载: {len(self.knowledge_chunks)} 个片段 "
                          f"(来自 {len(txt_files)} 个文件)")
                    return
                else:
                    print(f"[DocIndex] 知识库文件变更，重新解析...")
            except Exception as e:
                print(f"[DocIndex] 知识库缓存读取失败: {e}")

        # 全量解析
        for txt_path in txt_files:
            try:
                text = txt_path.read_text(encoding="utf-8")
                rel = txt_path.relative_to(self._doc_dir)
                source = str(rel.with_suffix("")).replace("\\", "/")
                chunks = self._parse_txt_sections(text, source)
                self.knowledge_chunks.extend(chunks)
            except Exception as e:
                print(f"[DocIndex] 读取知识库 {txt_path.name} 失败: {e}")

        if self.knowledge_chunks:
            print(f"[DocIndex] 知识库加载: {len(self.knowledge_chunks)} 个片段 "
                  f"(来自 {len(txt_files)} 个文件)")

            try:
                cache_data = {
                    "fingerprints": file_fingerprints,
                    "chunks": [
                        {
                            "title": c.title,
                            "content": c.content,
                            "source": c.source,
                            "keywords": c.keywords,
                        }
                        for c in self.knowledge_chunks
                    ],
                }
                with open(kb_cache_file, "w", encoding="utf-8") as f:
                    json.dump(cache_data, f, ensure_ascii=False, separators=(",", ":"))
                print(f"[DocIndex] 知识库缓存已保存")
            except Exception as e:
                print(f"[DocIndex] 知识库缓存保存失败: {e}")

    @staticmethod
    def _parse_txt_sections(text: str, source: str) -> List[KnowledgeChunk]:
        """将 .txt 文件按 ## 标题分段"""
        chunks: List[KnowledgeChunk] = []
        current_title = ""
        current_lines: List[str] = []

        def _flush():
            if current_title and current_lines:
                content = '\n'.join(current_lines).strip()
                if len(content) > 30:
                    keywords_en = [w.lower() for w in
                                   re.findall(r'[a-zA-Z_@][a-zA-Z0-9_@.]*', current_title + ' ' + content)
                                   if len(w) >= 2]
                    keywords_cn = re.findall(r'[\u4e00-\u9fff]{2,}', current_title)
                    all_kw = list(set(keywords_en + keywords_cn))
                    chunks.append(KnowledgeChunk(
                        title=current_title,
                        content=content[:2000],
                        source=source,
                        keywords=all_kw[:50],
                    ))

        for line in text.split('\n'):
            m = re.match(r'^##\s+(.+)', line)
            if m:
                title_text = m.group(1).strip()
                if re.match(r'^[=\-#*~]{3,}$', title_text):
                    continue
                _flush()
                current_title = title_text
                current_lines = []
            else:
                current_lines.append(line)

        _flush()
        return chunks

    # ==========================================================
    # 缓存序列化
    # ==========================================================

    def _save_to_cache(self, path: Path):
        data = {
            "version": 1,
            "waapi": {
                k: {"uri": v.uri, "description": v.description,
                     "category": v.category, "args": v.args}
                for k, v in self.waapi_index.items()
            },
            "object_types": {
                k: {"type_name": v.type_name, "description": v.description,
                     "properties": v.properties}
                for k, v in self.object_type_index.items()
            },
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

    def _load_from_cache(self, data: dict):
        for k, v in data.get("waapi", {}).items():
            self.waapi_index[k] = WaapiDoc(**v)
            cat = v.get("category", "")
            if cat:
                self._waapi_categories.setdefault(cat, []).append(k)

        for k, v in data.get("object_types", {}).items():
            self.object_type_index[k] = ObjectTypeDoc(**v)

        self._build_aliases()

    # ==========================================================
    # 查询 API
    # ==========================================================

    def lookup_waapi(self, uri: str) -> Optional[WaapiDoc]:
        """精确查找 WAAPI 函数"""
        return self.waapi_index.get(uri) or self.waapi_index.get(uri.lower())

    def lookup_object_type(self, type_name: str) -> Optional[ObjectTypeDoc]:
        """精确查找对象类型"""
        doc = self.object_type_index.get(type_name)
        if doc:
            return doc
        alias = self._type_aliases.get(type_name.lower())
        return self.object_type_index.get(alias) if alias else None

    def search_knowledge(self, query: str, top_k: int = 3) -> List[dict]:
        """在知识库中搜索与查询匹配的片段"""
        if not self.knowledge_chunks:
            return []

        ql = query.lower()
        query_words = set(re.findall(r'[a-zA-Z_@][a-zA-Z0-9_@.]*', ql))
        query_cn = set(re.findall(r'[\u4e00-\u9fff]{2,}', query))

        scored: List[tuple] = []
        for chunk in self.knowledge_chunks:
            score = 0.0
            chunk_kw_set = set(chunk.keywords)
            matched = query_words & chunk_kw_set
            score += len(matched) * 0.3
            for cn in query_cn:
                if cn in chunk.title or cn in chunk.content[:200]:
                    score += 0.5
            for w in query_words:
                if len(w) >= 3 and w in chunk.title.lower():
                    score += 0.8
            if score > 0.2:
                scored.append((score, chunk))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for score, chunk in scored[:top_k]:
            snippet = chunk.content[:300]
            if len(chunk.content) > 300:
                snippet += "..."
            results.append({
                "type": "knowledge",
                "name": chunk.title,
                "snippet": f"[知识库] {chunk.title}\n{snippet}",
                "score": min(score, 1.0),
                "source": chunk.source,
            })
        return results

    def search(self, query: str, top_k: int = 5, **_kw) -> List[dict]:
        """多策略搜索

        Returns:
            [{"type": "waapi"/"object_type"/"knowledge", "name": str,
              "snippet": str, "score": float}, ...]
        """
        results: List[dict] = []
        ql = query.lower().strip()

        # --- 精确匹配 ---
        waapi = self.lookup_waapi(ql)
        if waapi:
            results.append({"type": "waapi", "name": waapi.uri,
                            "snippet": self._fmt_waapi(waapi), "score": 1.0})

        obj_type = self.lookup_object_type(ql)
        if not obj_type:
            obj_type = self.lookup_object_type(query)
        if obj_type:
            results.append({"type": "object_type", "name": obj_type.type_name,
                            "snippet": self._fmt_object_type(obj_type), "score": 1.0})

        # --- 子串匹配 ---
        if len(results) < top_k:
            words = {w for w in re.findall(r"[a-zA-Z_][a-zA-Z0-9_.]{2,}", ql)}
            seen = {r["name"] for r in results}

            for w in words:
                if len(results) >= top_k:
                    break
                for uri, d in self.waapi_index.items():
                    if w in uri.lower() and uri not in seen:
                        results.append({"type": "waapi", "name": uri,
                                        "snippet": self._fmt_waapi(d), "score": 0.5})
                        seen.add(uri)
                        if len(results) >= top_k:
                            break
                for tname, d in self.object_type_index.items():
                    if w in tname.lower() and tname not in seen:
                        results.append({"type": "object_type", "name": tname,
                                        "snippet": self._fmt_object_type(d), "score": 0.4})
                        seen.add(tname)
                        if len(results) >= top_k:
                            break

        # --- 知识库匹配 ---
        if len(results) < top_k:
            kb_results = self.search_knowledge(query, top_k=top_k - len(results))
            seen = {r["name"] for r in results}
            for kr in kb_results:
                if kr["name"] not in seen:
                    results.append(kr)
                    seen.add(kr["name"])

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    # ==========================================================
    # 自动检索（供 _run_agent 注入上下文）
    # ==========================================================

    _STOP_WORDS = frozenset({
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "can", "shall", "to", "of", "in", "for",
        "on", "with", "at", "by", "from", "as", "into", "through", "about",
        "after", "before", "between", "under", "above", "up", "down", "out",
        "off", "over", "then", "than", "so", "no", "not", "only", "very",
        "just", "that", "this", "but", "and", "or", "if", "it", "its",
        "all", "each", "every", "both", "few", "more", "most", "some", "any",
        "how", "what", "which", "who", "when", "where", "why",
        "i", "you", "he", "she", "we", "they", "me", "him", "her", "us",
        "my", "your", "his", "our", "their",
        "new", "use", "get", "set", "run", "add", "create", "make",
        "want", "need", "try", "like", "also", "now", "one", "two",
        "using", "used", "function", "value", "values",
        "type", "name", "input", "output", "result", "data", "file",
        "string", "int", "float", "true", "false", "none", "null", "return",
    })

    def auto_retrieve(self, user_message: str, max_chars: int = 1200) -> str:
        """从用户消息中自动提取关键词并检索相关文档

        返回一段紧凑的文档片段，用于注入 AI 上下文。
        设计原则：宁精勿滥，每次最多注入 ~300 token。
        """
        if not any((self.waapi_index, self.object_type_index)):
            return ""

        snippets: List[str] = []
        seen: set = set()
        total = 0

        def _add(s: str, key: str):
            nonlocal total
            if key in seen or total + len(s) > max_chars:
                return
            seen.add(key)
            snippets.append(s)
            total += len(s)

        # 1) ak.wwise.* WAAPI 引用
        for ref in re.findall(r"ak\.wwise\.[a-zA-Z0-9_.]+", user_message):
            doc = self.lookup_waapi(ref)
            if doc:
                _add(self._fmt_waapi(doc), ref)

        # 2) 提取英文单词匹配
        words = set(re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", user_message))
        for w in words:
            wl = w.lower()
            if wl in self._STOP_WORDS or len(wl) < 3:
                continue
            # WAAPI 函数（匹配尾部）
            for uri, doc in self.waapi_index.items():
                if uri.endswith(f".{wl}") or uri.endswith(f".{w}"):
                    _add(self._fmt_waapi(doc), uri)
                    break
            # 对象类型
            tdoc = self.object_type_index.get(w) or self.object_type_index.get(wl)
            if not tdoc:
                alias = self._type_aliases.get(wl)
                if alias:
                    tdoc = self.object_type_index.get(alias)
            if tdoc:
                _add(self._fmt_object_type(tdoc), tdoc.type_name)

        # 3) 中文关键词匹配
        for kw in re.findall(r'[\u4e00-\u9fff]{2,}', user_message)[:3]:
            for tname, tdoc in self.object_type_index.items():
                if kw in tdoc.description:
                    _add(self._fmt_object_type(tdoc), tname)
                    break

        # 4) 知识库匹配
        if self.knowledge_chunks:
            _KB_HINTS = {
                # WAAPI
                "waapi", "ak.wwise", "api", "函数", "接口", "调用",
                # 对象类型
                "sound", "event", "bus", "container", "switch", "state",
                "rtpc", "effect", "soundbank", "trigger", "music",
                "actor-mixer", "random", "sequence", "blend",
                # 音频概念
                "音频", "声音", "混音", "音量", "衰减", "空间化",
                "attenuation", "spatialization", "positioning", "距离",
                "occlusion", "obstruction", "reverb", "混响",
                "interactive", "交互", "动态", "随机化",
                # Wwise 特有概念
                "work unit", "soundbank", "profiler", "capture",
                "game sync", "game parameter", "conversion",
            }
            msg_lower = user_message.lower()
            if any(h in msg_lower for h in _KB_HINTS):
                kb_results = self.search_knowledge(user_message, top_k=2)
                for kr in kb_results:
                    if kr["score"] > 0.3:
                        _add(kr["snippet"], kr["name"])

        if not snippets:
            return ""
        return "[Wwise 文档参考]\n" + "\n".join(snippets)

    # ==========================================================
    # WAAPI 目录生成（供 system prompt 注入）
    # ==========================================================

    _waapi_catalog_cache: Optional[str] = None

    def get_waapi_catalog(self) -> str:
        """生成紧凑的 WAAPI 函数目录，供注入 system prompt

        按分类输出常用 WAAPI 函数列表。
        """
        if self._waapi_catalog_cache is not None:
            return self._waapi_catalog_cache

        if not self._waapi_categories:
            self._waapi_catalog_cache = ""
            return ""

        lines = [f"Available WAAPI Functions ({len(self.waapi_index)}) - use search_local_doc for details:"]
        for cat in sorted(self._waapi_categories.keys()):
            uris = self._waapi_categories[cat]
            # 只显示短名
            short_names = sorted(set(uri.split(".")[-1] for uri in uris))
            lines.append(f"  [{cat}] {', '.join(short_names)}")

        catalog = '\n'.join(lines)
        self._waapi_catalog_cache = catalog
        return catalog

    # --- 格式化 ---

    @staticmethod
    def _fmt_waapi(d: WaapiDoc) -> str:
        s = f"[WAAPI] {d.uri}"
        if d.description:
            s += f": {d.description[:120]}"
        if d.args:
            s += f"\n   Args: {', '.join(d.args[:6])}"
        return s

    @staticmethod
    def _fmt_object_type(d: ObjectTypeDoc) -> str:
        s = f"[Type] {d.type_name}"
        if d.description:
            s += f": {d.description[:120]}"
        if d.properties:
            s += f"\n   Props: {', '.join(d.properties[:8])}"
        return s


# ============================================================
# 全局单例
# ============================================================

_index_instance: Optional[WwiseDocIndex] = None


def get_doc_index(doc_dir: Optional[str] = None) -> WwiseDocIndex:
    """获取全局文档索引实例（单例）"""
    global _index_instance
    if _index_instance is None:
        _index_instance = WwiseDocIndex(doc_dir)
    return _index_instance


# 兼容 API
get_doc_rag = get_doc_index
