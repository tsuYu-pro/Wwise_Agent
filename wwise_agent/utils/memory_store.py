# -*- coding: utf-8 -*-
"""
三层记忆存储模块 (Memory Store)

使用 SQLite + 本地 Embedding 实现：
- Episodic Memory  (事件记忆：具体经历)
- Semantic Memory  (语义记忆：反思生成的经验规则)
- Procedural Memory (策略记忆：解决问题的套路)

向量检索使用 numpy cosine similarity（记忆条目通常 <10000 条，无需 FAISS）。
"""

import json
import math
import sqlite3
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from .embedding import get_embedder, LocalEmbedder, EMBEDDING_DIM

# ============================================================
# 数据库路径
# ============================================================

_DB_DIR = Path(__file__).parent.parent.parent / "cache" / "memory"
_DB_PATH = _DB_DIR / "agent_memory.db"

# ============================================================
# 数据类
# ============================================================

@dataclass
class EpisodicRecord:
    """事件记忆记录"""
    id: str = ""
    timestamp: float = 0.0
    session_id: str = ""
    task_description: str = ""
    actions: List[dict] = field(default_factory=list)
    result_summary: str = ""
    success: bool = True
    error_count: int = 0
    retry_count: int = 0
    reward_score: float = 0.0
    embedding: Optional[np.ndarray] = None
    importance: float = 1.0
    tags: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if self.timestamp == 0.0:
            self.timestamp = time.time()


@dataclass
class SemanticRecord:
    """语义记忆记录（抽象知识/规则）"""
    id: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0
    rule: str = ""
    source_episodes: List[str] = field(default_factory=list)
    confidence: float = 0.5
    activation_count: int = 0
    embedding: Optional[np.ndarray] = None
    category: str = "general"

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        now = time.time()
        if self.created_at == 0.0:
            self.created_at = now
        if self.updated_at == 0.0:
            self.updated_at = now


@dataclass
class ProceduralRecord:
    """策略记忆记录"""
    id: str = ""
    strategy_name: str = ""
    description: str = ""
    priority: float = 0.5
    success_rate: float = 0.5
    usage_count: int = 0
    last_used: float = 0.0
    embedding: Optional[np.ndarray] = None
    conditions: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if self.last_used == 0.0:
            self.last_used = time.time()


# ============================================================
# Memory Store 核心类
# ============================================================

class MemoryStore:
    """三层记忆 SQLite 存储 + Embedding 向量检索"""

    def __init__(self, db_path: Optional[Path] = None, embedder: Optional[LocalEmbedder] = None):
        self.db_path = db_path or _DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.embedder = embedder or get_embedder()
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    # ==========================================================
    # 数据库初始化
    # ==========================================================

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
        return self._conn

    def _init_db(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS episodic_memory (
                id TEXT PRIMARY KEY,
                timestamp REAL,
                session_id TEXT,
                task_description TEXT,
                actions TEXT,
                result_summary TEXT,
                success INTEGER,
                error_count INTEGER,
                retry_count INTEGER,
                reward_score REAL,
                embedding BLOB,
                importance REAL,
                tags TEXT
            );

            CREATE TABLE IF NOT EXISTS semantic_memory (
                id TEXT PRIMARY KEY,
                created_at REAL,
                updated_at REAL,
                rule TEXT,
                source_episodes TEXT,
                confidence REAL,
                activation_count INTEGER,
                embedding BLOB,
                category TEXT
            );

            CREATE TABLE IF NOT EXISTS procedural_memory (
                id TEXT PRIMARY KEY,
                strategy_name TEXT,
                description TEXT,
                priority REAL,
                success_rate REAL,
                usage_count INTEGER,
                last_used REAL,
                embedding BLOB,
                conditions TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_episodic_session ON episodic_memory(session_id);
            CREATE INDEX IF NOT EXISTS idx_episodic_timestamp ON episodic_memory(timestamp);
            CREATE INDEX IF NOT EXISTS idx_episodic_importance ON episodic_memory(importance);
            CREATE INDEX IF NOT EXISTS idx_semantic_category ON semantic_memory(category);
            CREATE INDEX IF NOT EXISTS idx_semantic_confidence ON semantic_memory(confidence);
            CREATE INDEX IF NOT EXISTS idx_procedural_priority ON procedural_memory(priority);
        """)
        conn.commit()

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    # ==========================================================
    # Episodic Memory CRUD
    # ==========================================================

    def add_episodic(self, record: EpisodicRecord) -> str:
        if record.embedding is None:
            text = f"{record.task_description} {record.result_summary}"
            record.embedding = self.embedder.encode(text)
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO episodic_memory
               (id, timestamp, session_id, task_description, actions,
                result_summary, success, error_count, retry_count,
                reward_score, embedding, importance, tags)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                record.id, record.timestamp, record.session_id,
                record.task_description,
                json.dumps(record.actions, ensure_ascii=False),
                record.result_summary,
                1 if record.success else 0,
                record.error_count, record.retry_count,
                record.reward_score,
                self.embedder.to_bytes(record.embedding),
                record.importance,
                json.dumps(record.tags, ensure_ascii=False),
            ),
        )
        conn.commit()
        return record.id

    def get_episodic(self, record_id: str) -> Optional[EpisodicRecord]:
        row = self._get_conn().execute(
            "SELECT * FROM episodic_memory WHERE id=?", (record_id,)
        ).fetchone()
        return self._row_to_episodic(row) if row else None

    def get_recent_episodic(self, limit: int = 20) -> List[EpisodicRecord]:
        rows = self._get_conn().execute(
            "SELECT * FROM episodic_memory ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._row_to_episodic(r) for r in rows]

    def search_episodic(self, query: str, top_k: int = 5, min_importance: float = 0.1) -> List[Tuple[EpisodicRecord, float]]:
        """向量检索事件记忆, returns [(record, score), ...]"""
        query_vec = self.embedder.encode(query)
        rows = self._get_conn().execute(
            "SELECT * FROM episodic_memory WHERE importance >= ? ORDER BY importance DESC",
            (min_importance,)
        ).fetchall()
        if not rows:
            return []
        results = []
        for row in rows:
            rec = self._row_to_episodic(row)
            if rec.embedding is not None:
                sim = self.embedder.cosine_similarity(query_vec, rec.embedding)
                combined = sim * (0.5 + 0.5 * min(rec.importance, 2.0))
                results.append((rec, combined))
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def update_episodic_importance(self, record_id: str, new_importance: float):
        conn = self._get_conn()
        conn.execute("UPDATE episodic_memory SET importance=? WHERE id=?", (new_importance, record_id))
        conn.commit()

    def update_episodic_reward(self, record_id: str, reward_score: float, importance: float):
        conn = self._get_conn()
        conn.execute(
            "UPDATE episodic_memory SET reward_score=?, importance=? WHERE id=?",
            (reward_score, importance, record_id)
        )
        conn.commit()

    def update_episodic_tags(self, record_id: str, tags: List[str]):
        conn = self._get_conn()
        conn.execute(
            "UPDATE episodic_memory SET tags=? WHERE id=?",
            (json.dumps(tags, ensure_ascii=False), record_id)
        )
        conn.commit()

    def count_episodic(self) -> int:
        return self._get_conn().execute("SELECT COUNT(*) FROM episodic_memory").fetchone()[0]

    def get_episodic_by_session(self, session_id: str) -> List[EpisodicRecord]:
        rows = self._get_conn().execute(
            "SELECT * FROM episodic_memory WHERE session_id=? ORDER BY timestamp ASC",
            (session_id,)
        ).fetchall()
        return [self._row_to_episodic(r) for r in rows]

    # ==========================================================
    # Semantic Memory CRUD
    # ==========================================================

    def add_semantic(self, record: SemanticRecord) -> str:
        if record.embedding is None:
            record.embedding = self.embedder.encode(record.rule)
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO semantic_memory
               (id, created_at, updated_at, rule, source_episodes,
                confidence, activation_count, embedding, category)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                record.id, record.created_at, record.updated_at,
                record.rule,
                json.dumps(record.source_episodes, ensure_ascii=False),
                record.confidence, record.activation_count,
                self.embedder.to_bytes(record.embedding),
                record.category,
            ),
        )
        conn.commit()
        return record.id

    def get_semantic(self, record_id: str) -> Optional[SemanticRecord]:
        row = self._get_conn().execute(
            "SELECT * FROM semantic_memory WHERE id=?", (record_id,)
        ).fetchone()
        return self._row_to_semantic(row) if row else None

    def search_semantic(self, query: str, top_k: int = 5, min_confidence: float = 0.2) -> List[Tuple[SemanticRecord, float]]:
        query_vec = self.embedder.encode(query)
        rows = self._get_conn().execute(
            "SELECT * FROM semantic_memory WHERE confidence >= ?", (min_confidence,)
        ).fetchall()
        if not rows:
            return []
        results = []
        for row in rows:
            rec = self._row_to_semantic(row)
            if rec.embedding is not None:
                sim = self.embedder.cosine_similarity(query_vec, rec.embedding)
                combined = sim * (0.5 + 0.5 * rec.confidence)
                results.append((rec, combined))
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def get_all_semantic(self, category: Optional[str] = None) -> List[SemanticRecord]:
        conn = self._get_conn()
        if category:
            rows = conn.execute(
                "SELECT * FROM semantic_memory WHERE category=? ORDER BY confidence DESC",
                (category,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM semantic_memory ORDER BY confidence DESC"
            ).fetchall()
        return [self._row_to_semantic(r) for r in rows]

    def increment_semantic_activation(self, record_id: str):
        conn = self._get_conn()
        conn.execute(
            "UPDATE semantic_memory SET activation_count = activation_count + 1, updated_at=? WHERE id=?",
            (time.time(), record_id)
        )
        conn.commit()

    def update_semantic_confidence(self, record_id: str, confidence: float):
        conn = self._get_conn()
        conn.execute(
            "UPDATE semantic_memory SET confidence=?, updated_at=? WHERE id=?",
            (confidence, time.time(), record_id)
        )
        conn.commit()

    def find_duplicate_semantic(self, rule_text: str, threshold: float = 0.85) -> Optional[SemanticRecord]:
        results = self.search_semantic(rule_text, top_k=1, min_confidence=0.0)
        if results and results[0][1] >= threshold:
            return results[0][0]
        return None

    def count_semantic(self) -> int:
        return self._get_conn().execute("SELECT COUNT(*) FROM semantic_memory").fetchone()[0]

    # ==========================================================
    # Procedural Memory CRUD
    # ==========================================================

    def add_procedural(self, record: ProceduralRecord) -> str:
        if record.embedding is None:
            text = f"{record.strategy_name}: {record.description}"
            record.embedding = self.embedder.encode(text)
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO procedural_memory
               (id, strategy_name, description, priority, success_rate,
                usage_count, last_used, embedding, conditions)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                record.id, record.strategy_name, record.description,
                record.priority, record.success_rate,
                record.usage_count, record.last_used,
                self.embedder.to_bytes(record.embedding),
                json.dumps(record.conditions, ensure_ascii=False),
            ),
        )
        conn.commit()
        return record.id

    def get_procedural(self, record_id: str) -> Optional[ProceduralRecord]:
        row = self._get_conn().execute(
            "SELECT * FROM procedural_memory WHERE id=?", (record_id,)
        ).fetchone()
        return self._row_to_procedural(row) if row else None

    def search_procedural(self, query: str, top_k: int = 3) -> List[Tuple[ProceduralRecord, float]]:
        query_vec = self.embedder.encode(query)
        rows = self._get_conn().execute(
            "SELECT * FROM procedural_memory ORDER BY priority DESC"
        ).fetchall()
        if not rows:
            return []
        results = []
        for row in rows:
            rec = self._row_to_procedural(row)
            if rec.embedding is not None:
                sim = self.embedder.cosine_similarity(query_vec, rec.embedding)
                combined = sim * (0.3 + 0.7 * rec.priority)
                results.append((rec, combined))
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def get_all_procedural(self) -> List[ProceduralRecord]:
        rows = self._get_conn().execute(
            "SELECT * FROM procedural_memory ORDER BY priority DESC"
        ).fetchall()
        return [self._row_to_procedural(r) for r in rows]

    def update_procedural_usage(self, record_id: str, success: bool):
        conn = self._get_conn()
        rec = self.get_procedural(record_id)
        if not rec:
            return
        rec.usage_count += 1
        rec.last_used = time.time()
        alpha = min(0.3, 1.0 / rec.usage_count)
        rec.success_rate = (1 - alpha) * rec.success_rate + alpha * (1.0 if success else 0.0)
        conn.execute(
            "UPDATE procedural_memory SET usage_count=?, last_used=?, success_rate=? WHERE id=?",
            (rec.usage_count, rec.last_used, rec.success_rate, record_id)
        )
        conn.commit()

    def update_procedural_priority(self, record_id: str, priority_delta: float):
        conn = self._get_conn()
        conn.execute(
            "UPDATE procedural_memory SET priority = MIN(1.0, MAX(0.0, priority + ?)) WHERE id=?",
            (priority_delta, record_id)
        )
        conn.commit()

    def count_procedural(self) -> int:
        return self._get_conn().execute("SELECT COUNT(*) FROM procedural_memory").fetchone()[0]

    def get_procedural_by_name(self, name: str) -> Optional[ProceduralRecord]:
        row = self._get_conn().execute(
            "SELECT * FROM procedural_memory WHERE strategy_name=?", (name,)
        ).fetchone()
        return self._row_to_procedural(row) if row else None

    # ==========================================================
    # 全局重要度衰减
    # ==========================================================

    def decay_importance(self, lambda_decay: float = 0.01):
        """importance *= exp(-lambda * days_since_creation)"""
        conn = self._get_conn()
        now = time.time()
        rows = conn.execute("SELECT id, timestamp, importance FROM episodic_memory").fetchall()
        for row_id, ts, imp in rows:
            days = (now - ts) / 86400.0
            new_imp = imp * math.exp(-lambda_decay * days)
            new_imp = max(new_imp, 0.01)
            if abs(new_imp - imp) > 0.001:
                conn.execute("UPDATE episodic_memory SET importance=? WHERE id=?", (new_imp, row_id))
        conn.commit()

    # ==========================================================
    # 统计信息
    # ==========================================================

    def get_stats(self) -> Dict:
        return {
            "episodic_count": self.count_episodic(),
            "semantic_count": self.count_semantic(),
            "procedural_count": self.count_procedural(),
            "backend": self.embedder._backend,
            "embedding_dim": self.embedder.dim,
        }

    # ==========================================================
    # 内部工具方法
    # ==========================================================

    def _row_to_episodic(self, row) -> EpisodicRecord:
        return EpisodicRecord(
            id=row[0], timestamp=row[1], session_id=row[2],
            task_description=row[3],
            actions=json.loads(row[4]) if row[4] else [],
            result_summary=row[5],
            success=bool(row[6]),
            error_count=row[7], retry_count=row[8],
            reward_score=row[9],
            embedding=self.embedder.from_bytes(row[10]) if row[10] else None,
            importance=row[11],
            tags=json.loads(row[12]) if row[12] else [],
        )

    def _row_to_semantic(self, row) -> SemanticRecord:
        return SemanticRecord(
            id=row[0], created_at=row[1], updated_at=row[2],
            rule=row[3],
            source_episodes=json.loads(row[4]) if row[4] else [],
            confidence=row[5], activation_count=row[6],
            embedding=self.embedder.from_bytes(row[7]) if row[7] else None,
            category=row[8],
        )

    def _row_to_procedural(self, row) -> ProceduralRecord:
        return ProceduralRecord(
            id=row[0], strategy_name=row[1], description=row[2],
            priority=row[3], success_rate=row[4],
            usage_count=row[5], last_used=row[6],
            embedding=self.embedder.from_bytes(row[7]) if row[7] else None,
            conditions=json.loads(row[8]) if row[8] else [],
        )

    # ==========================================================
    # 初始化默认策略（Wwise 领域）
    # ==========================================================

    def seed_default_strategies(self):
        """写入 Wwise 领域默认策略（首次运行时调用）"""
        if self.count_procedural() > 0:
            return

        defaults = [
            ProceduralRecord(
                strategy_name="decompose_complex_task",
                description="Complex audio design tasks should be decomposed into sub-steps: create hierarchy, set properties, create events, configure buses",
                priority=0.7,
                conditions=["task_complexity > high", "tool_calls > 5"],
            ),
            ProceduralRecord(
                strategy_name="verify_before_modify",
                description="Before modifying Wwise objects, query current hierarchy and properties to understand existing state",
                priority=0.65,
                conditions=["action_type == modify", "target_unknown"],
            ),
            ProceduralRecord(
                strategy_name="error_recovery",
                description="When a WAAPI call fails, analyze the error message and try alternative approaches instead of repeating the same call",
                priority=0.7,
                conditions=["error_occurred", "retry_count > 1"],
            ),
            ProceduralRecord(
                strategy_name="event_completeness_check",
                description="After creating sound objects and events, verify the complete chain: Sound → Event → Action → Bus routing",
                priority=0.6,
                conditions=["event_creation", "sound_design"],
            ),
            ProceduralRecord(
                strategy_name="bus_hierarchy_awareness",
                description="Always check the Master-Mixer hierarchy before assigning buses; verify the target bus exists",
                priority=0.55,
                conditions=["bus_assignment", "routing_change"],
            ),
        ]

        for s in defaults:
            self.add_procedural(s)
        print(f"[MemoryStore] Seeded {len(defaults)} default strategies (Wwise)")


# ============================================================
# 全局单例
# ============================================================

_store_instance: Optional[MemoryStore] = None

def get_memory_store() -> MemoryStore:
    """获取全局 MemoryStore 实例"""
    global _store_instance
    if _store_instance is None:
        _store_instance = MemoryStore()
        _store_instance.seed_default_strategies()
    return _store_instance
