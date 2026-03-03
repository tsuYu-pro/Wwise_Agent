# -*- coding: utf-8 -*-
"""
本地 Embedding 封装模块

使用 sentence-transformers 的 all-MiniLM-L6-v2 模型生成文本向量。
支持批量编码、缓存、以及无模型时的 fallback（字符 n-gram 哈希向量）。

向量维度: 384 (all-MiniLM-L6-v2)
"""

import hashlib
import numpy as np
from pathlib import Path
from typing import List, Optional

# ============================================================
# 常量
# ============================================================

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384
_MODEL_CACHE_DIR = Path(__file__).parent.parent.parent / "cache" / "memory" / "embeddings"

# ============================================================
# 全局单例
# ============================================================
_embedder_instance = None


class LocalEmbedder:
    """本地文本 Embedding 编码器

    加载优先级:
    1. sentence-transformers (最优质量)
    2. 纯 fallback: 基于字符 n-gram 的伪向量 (零依赖，质量有限但可用)
    """

    def __init__(self, model_name: str = DEFAULT_MODEL, cache_dir: Optional[Path] = None):
        self.model_name = model_name
        self.cache_dir = cache_dir or _MODEL_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.dim = EMBEDDING_DIM
        self._model = None
        self._backend = "none"
        self._encode_cache = {}
        self._max_cache = 2000

        self._try_load_model()

    # ==========================================================
    # 模型加载
    # ==========================================================

    def _try_load_model(self):
        """尝试加载 sentence-transformers 模型"""
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(
                self.model_name,
                cache_folder=str(self.cache_dir),
            )
            self._backend = "sentence-transformers"
            self.dim = self._model.get_sentence_embedding_dimension()
            print(f"[Embedding] Loaded: {self.model_name} (dim={self.dim}, backend=sentence-transformers)")
            return
        except ImportError:
            print("[Embedding] sentence-transformers not installed")
        except Exception as e:
            print(f"[Embedding] sentence-transformers load failed: {e}")

        self._backend = "fallback"
        self.dim = EMBEDDING_DIM
        print(f"[Embedding] Using fallback mode (n-gram hash, dim={self.dim})")

    @property
    def is_semantic(self) -> bool:
        """是否使用真正的语义模型（非 fallback）"""
        return self._backend == "sentence-transformers"

    # ==========================================================
    # 编码接口
    # ==========================================================

    def encode(self, text: str) -> np.ndarray:
        """将单条文本编码为归一化后的 float32 向量, shape=(dim,)"""
        if not text or not text.strip():
            return np.zeros(self.dim, dtype=np.float32)

        cache_key = hashlib.md5(text.encode('utf-8', errors='ignore')).hexdigest()
        if cache_key in self._encode_cache:
            return self._encode_cache[cache_key]

        if self._backend == "sentence-transformers":
            vec = self._model.encode(text, show_progress_bar=False, normalize_embeddings=True)
            vec = np.array(vec, dtype=np.float32)
        else:
            vec = self._encode_fallback(text)

        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        vec = vec.astype(np.float32)

        if len(self._encode_cache) >= self._max_cache:
            keys = list(self._encode_cache.keys())
            for k in keys[:len(keys) // 5]:
                del self._encode_cache[k]
        self._encode_cache[cache_key] = vec

        return vec

    def encode_batch(self, texts: List[str]) -> np.ndarray:
        """批量编码, shape=(len(texts), dim)"""
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        if self._backend == "sentence-transformers":
            vecs = self._model.encode(texts, show_progress_bar=False,
                                      normalize_embeddings=True, batch_size=32)
            return np.array(vecs, dtype=np.float32)
        return np.array([self.encode(t) for t in texts], dtype=np.float32)

    # ==========================================================
    # Fallback: 基于字符 n-gram 的伪向量
    # ==========================================================

    def _encode_fallback(self, text: str) -> np.ndarray:
        """基于字符 3-gram 的哈希向量（不是真正的语义向量，但能捕捉词汇重叠）"""
        vec = np.zeros(self.dim, dtype=np.float32)
        text_lower = text.lower().strip()
        if not text_lower:
            return vec

        for i in range(len(text_lower) - 2):
            ngram = text_lower[i:i+3]
            h = int(hashlib.md5(ngram.encode()).hexdigest(), 16)
            idx = h % self.dim
            vec[idx] += 1.0

        words = text_lower.split()
        for w in words:
            if len(w) >= 2:
                h = int(hashlib.md5(w.encode()).hexdigest(), 16)
                idx = h % self.dim
                vec[idx] += 2.0

        return vec

    # ==========================================================
    # 相似度计算
    # ==========================================================

    @staticmethod
    def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """计算两个向量的余弦相似度"""
        if a is None or b is None:
            return 0.0
        dot = np.dot(a, b)
        return float(np.clip(dot, -1.0, 1.0))

    @staticmethod
    def batch_cosine_similarity(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
        """计算 query 与矩阵中每行的余弦相似度"""
        if query is None or matrix is None or len(matrix) == 0:
            return np.array([], dtype=np.float32)
        scores = matrix @ query
        return np.clip(scores, -1.0, 1.0)

    # ==========================================================
    # 序列化辅助
    # ==========================================================

    @staticmethod
    def to_bytes(vec: np.ndarray) -> bytes:
        """将向量序列化为 bytes（存入 SQLite BLOB）"""
        return vec.astype(np.float32).tobytes()

    @staticmethod
    def from_bytes(data: bytes, dim: int = EMBEDDING_DIM) -> np.ndarray:
        """从 bytes 反序列化为向量"""
        if not data:
            return np.zeros(dim, dtype=np.float32)
        return np.frombuffer(data, dtype=np.float32).copy()


# ============================================================
# 全局单例
# ============================================================

def get_embedder(model_name: str = DEFAULT_MODEL) -> LocalEmbedder:
    """获取全局 Embedding 编码器实例（单例）"""
    global _embedder_instance
    if _embedder_instance is None:
        _embedder_instance = LocalEmbedder(model_name)
    return _embedder_instance
