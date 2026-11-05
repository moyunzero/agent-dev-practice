"""第 2 课：定义 schema 并创建 collection。"""

from pymilvus import MilvusClient

from milvus_config import COLLECTION, DIM, MILVUS_URI


def main() -> None:
    client = MilvusClient(uri=MILVUS_URI)

    if client.has_collection(COLLECTION):
        client.drop_collection(COLLECTION)
        print(f"已删除旧 collection: {COLLECTION}")

    # MilvusClient 简版 schema：主键 id + 384 维向量 embedding
    client.create_collection(
        collection_name=COLLECTION,
        dimension=DIM,
        auto_id=False,
        primary_field_name="id",
        id_type="int",
        vector_field_name="embedding",
    )

    print(f"已创建 collection: {COLLECTION}")
    print(f"  向量维度 dim = {DIM}")
    print(f"  主键字段     id (int64，手动指定)")
    print(f"  向量字段     embedding (float_vector, dim={DIM})")
    print(f"  当前列表     {client.list_collections()}")
    print(
        """
【本课要点】
1. Collection ≈ 向量表；创建时必须声明向量 dim（与 Embedding 模型一致）。
2. dim 不一致时 insert/search 会报错 —— 384 对应 all-MiniLM-L6-v2。
3. 下节课：insert 文本向量 + search Top-K。
"""
    )


if __name__ == "__main__":
    main()
