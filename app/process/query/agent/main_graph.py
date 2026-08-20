"""查询 LangGraph 主图：查询理解、三路召回、融合、精排和答案。"""

from langgraph.graph import END, StateGraph

from app.process.query.agent.nodes.node_answer_output import node_answer_output
from app.process.query.agent.nodes.node_item_name_confirm import (
    node_item_name_confirm,
)
from app.process.query.agent.nodes.node_rerank import node_rerank
from app.process.query.agent.nodes.node_rrf import node_rrf
from app.process.query.agent.nodes.node_search_embedding import (
    node_search_embedding,
)
from app.process.query.agent.nodes.node_search_embedding_hyde import (
    node_search_embedding_hyde,
)
from app.process.query.agent.nodes.node_web_search_mcp import (
    node_web_search_mcp,
)
from app.process.query.agent.state import QueryGraphState
from app.shared.runtime.logger import logger


def route_after_query_understanding(
    state: QueryGraphState,
) -> str | tuple[str, str, str]:
    """有澄清回答时直接输出，否则并行启动三路检索。"""
    if state.get("answer"):
        logger.warning("查询需要澄清，跳过检索并进入答案输出节点")
        return "node_answer_output"
    if not state.get("rewritten_query"):
        logger.error("查询理解后缺少 rewritten_query 且没有澄清回答")
        raise RuntimeError("查询理解状态不完整")
    logger.info("查询理解完成，启动普通、HyDE 和 Web 三路并行检索")
    return (
        "node_search_embedding",
        "node_search_embedding_hyde",
        "node_web_search_mcp",
    )


query_graph = StateGraph(QueryGraphState)
query_graph.add_node("node_item_name_confirm", node_item_name_confirm)
query_graph.add_node("node_search_embedding", node_search_embedding)
query_graph.add_node(
    "node_search_embedding_hyde", node_search_embedding_hyde
)
query_graph.add_node("node_web_search_mcp", node_web_search_mcp)
query_graph.add_node("node_rrf", node_rrf)
query_graph.add_node("node_rerank", node_rerank)
query_graph.add_node("node_answer_output", node_answer_output)

query_graph.set_entry_point("node_item_name_confirm")
query_graph.add_conditional_edges(
    "node_item_name_confirm",
    route_after_query_understanding,
    {
        "node_answer_output": "node_answer_output",
        "node_search_embedding": "node_search_embedding",
        "node_search_embedding_hyde": "node_search_embedding_hyde",
        "node_web_search_mcp": "node_web_search_mcp",
    },
)

# 三条边汇入同一节点，LangGraph 在同一 superstep 完成后执行一次 RRF。
query_graph.add_edge("node_search_embedding", "node_rrf")
query_graph.add_edge("node_search_embedding_hyde", "node_rrf")
query_graph.add_edge("node_web_search_mcp", "node_rrf")
query_graph.add_edge("node_rrf", "node_rerank")
query_graph.add_edge("node_rerank", "node_answer_output")
query_graph.add_edge("node_answer_output", END)

query_app = query_graph.compile()

# 旧代码使用的路由函数名兼容。
node_item_name_confirm_after_router = route_after_query_understanding
