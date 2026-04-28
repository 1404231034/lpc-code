"""长期向量库记忆 — 基于 ChromaDB + sentence-transformers"""

import logging
from pathlib import Path
from typing import Any

import chromadb
from chromadb.utils import embedding_functions

logger = logging.getLogger(__name__)

# 自动存储的关键词信号
STORE_SIGNALS = [
    "记住", "记住这个", "这很重要", "别忘了", "记下来",
    "记住这点", "保存", "备注", "重要信息",
]


class LongTermMemory:
    """长期记忆，基于 ChromaDB 向量库"""

    def __init__(
        self,
        embedding_model: str = "all-MiniLM-L6-v2",
        persist_directory: str = "data/vectorstore",
        collection_name: str = "agent_memory",
    ) -> None:
        self._embedding_model_name = embedding_model
        self._persist_dir = Path(persist_directory)
        self._persist_dir.mkdir(parents=True, exist_ok=True)

        # 初始化 ChromaDB
        self._client = chromadb.PersistentClient(path=str(self._persist_dir))

        # 初始化嵌入函数
        try:
            self._embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=embedding_model,
            )
            logger.info(f"嵌入模型加载成功: {embedding_model}")
        except Exception as e:
            logger.warning(f"嵌入模型加载失败: {e}，使用默认嵌入")
            self._embedding_fn = embedding_functions.DefaultEmbeddingFunction()

        # 获取或创建集合
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            embedding_function=self._embedding_fn,
        )
        logger.info(f"长期记忆集合 '{collection_name}' 就绪，现有 {self._collection.count()} 条记录")

    def store(self, text: str, metadata: dict[str, Any] | None = None) -> None:
        """
        存储一条记忆。

        Args:
            text: 记忆文本
            metadata: 元数据（如来源、时间戳等）
        """
        if not text.strip():
            return

        import uuid
        doc_id = str(uuid.uuid4())
        meta = metadata or {}
        meta.setdefault("source", "conversation")

        self._collection.add(
            documents=[text],
            metadatas=[meta],
            ids=[doc_id],
        )
        logger.debug(f"存储记忆: {text[:50]}...")

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """
        语义搜索相关记忆。

        Args:
            query: 查询文本
            top_k: 返回结果数

        Returns:
            匹配的记忆列表
        """
        if self._collection.count() == 0:
            return []

        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=min(top_k, self._collection.count()),
            )

            items = []
            if results and results["documents"]:
                for i, doc in enumerate(results["documents"][0]):
                    item = {
                        "text": doc,
                        "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    }
                    if results["distances"] and results["distances"][0]:
                        item["distance"] = results["distances"][0][i]
                    items.append(item)

            return items

        except Exception as e:
            logger.error(f"记忆检索失败: {e}")
            return []

    def should_store(self, message: str) -> bool:
        """判断消息是否应该存入长期记忆"""
        msg_lower = message.lower()
        return any(signal in msg_lower for signal in STORE_SIGNALS)

    def count(self) -> int:
        """返回存储的记忆数量"""
        return self._collection.count()

    def clear(self) -> None:
        """清空所有记忆"""
        # 删除并重建集合
        name = self._collection.name
        self._client.delete_collection(name)
        self._collection = self._client.get_or_create_collection(
            name=name,
            embedding_function=self._embedding_fn,
        )
        logger.info("长期记忆已清空")
