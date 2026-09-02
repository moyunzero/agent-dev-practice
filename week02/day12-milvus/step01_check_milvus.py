"""第 1 课：连通 Milvus Standalone — 确认 Docker 服务与 SDK 可用。"""

from pymilvus import MilvusClient

from milvus_config import MILVUS_URI


def main() -> None:
    print(f"连接 Milvus {MILVUS_URI} ...")
    client = MilvusClient(uri=MILVUS_URI)

    version = client.get_server_version()
    print(f"Milvus 版本: {version}")

    collections = client.list_collections()
    print(f"当前 collections: {collections or '(空)'}")

    print(
        """
【本课要点】
1. Milvus 是独立服务，Python 通过 pymilvus 连 URI（不是 Chroma 本地文件）。
2. 本课 Docker 默认 19531（避免与已有 Milvus 19530 冲突）。
3. Standalone = Milvus + etcd（元数据）+ MinIO（对象存储）。
4. 输入：已启动的 Milvus + URI；输出：版本号 + collection 列表。
"""
    )


if __name__ == "__main__":
    main()
