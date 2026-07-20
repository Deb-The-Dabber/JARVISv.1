import json
import os
import re
import threading

import networkx as nx

GRAPH_PATH = os.path.join(os.path.expanduser("~"), "jarvis_graph.json")

_graph = nx.MultiDiGraph()
_lock = threading.Lock()


def load_graph():
    global _graph
    if not os.path.exists(GRAPH_PATH):
        _graph = nx.MultiDiGraph()
        return _graph
    try:
        with open(GRAPH_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        _graph = nx.node_link_graph(data, directed=True, multigraph=True)
    except Exception:
        _graph = nx.MultiDiGraph()
    return _graph


def save_graph():
    with _lock:
        data = nx.node_link_data(_graph)
        with open(GRAPH_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)


def add_entity(name: str, entity_type: str, properties: dict = None):
    if not name:
        return
    props = properties or {}
    existing = dict(_graph.nodes[name]) if _graph.has_node(name) else {}
    existing.update(props)
    existing["entity_type"] = entity_type or existing.get("entity_type", "concept")
    _graph.add_node(name, **existing)
    save_graph()


def add_relationship(entity1: str, relationship: str, entity2: str):
    if not entity1 or not relationship or not entity2:
        return
    if not _graph.has_node(entity1):
        _graph.add_node(entity1, entity_type="concept")
    if not _graph.has_node(entity2):
        _graph.add_node(entity2, entity_type="concept")
    _graph.add_edge(entity1, entity2, relationship=relationship)
    save_graph()


def query_relationships(entity: str) -> str:
    if not _graph.has_node(entity):
        return f"No knowledge graph entry found for {entity}."

    parts = []
    for _, target, data in _graph.out_edges(entity, data=True):
        parts.append(f"{data.get('relationship', 'related_to')} {target}")
    for source, _, data in _graph.in_edges(entity, data=True):
        parts.append(f"{data.get('relationship', 'related_to')} by {source}")

    props = {
        k: v
        for k, v in _graph.nodes[entity].items()
        if k != "entity_type"
    }
    prop_text = ", ".join(f"{k}: {v}" for k, v in props.items())
    rel_text = ", ".join(parts) if parts else "no relationships yet"
    return f"{entity}: {rel_text}" + (f". Properties: {prop_text}" if prop_text else "")


def find_connected(entity1: str, entity2: str) -> str:
    try:
        path = nx.shortest_path(_graph.to_undirected(), entity1, entity2)
    except Exception:
        return f"No connection found between {entity1} and {entity2}."

    pieces = [path[0]]
    for left, right in zip(path, path[1:]):
        edge_data = _graph.get_edge_data(left, right) or _graph.get_edge_data(right, left) or {}
        first_edge = next(iter(edge_data.values()), {})
        pieces.append(first_edge.get("relationship", "related_to"))
        pieces.append(right)
    return " -> ".join(pieces)


def get_all_entities(entity_type: str = None) -> list:
    entities = []
    for name, data in _graph.nodes(data=True):
        if entity_type and data.get("entity_type") != entity_type:
            continue
        entities.append({"name": name, **data})
    return entities


def extract_entities_relations(text: str) -> list[dict]:
    if not text or len(text.strip()) < 10:
        return []

    prompt = f"""Extract entities and relationships from this text as JSON.
Format: [{{"entity1": "", "relationship": "", "entity2": ""}}]
Only extract clear factual relationships. Return [] if none.
Text: {text[:2000]}"""

    try:
        from brain import ask_openrouter
        extraction = ask_openrouter(prompt, [])
    except Exception:
        try:
            from brain import ask_groq
            extraction = ask_groq(prompt, [])
        except Exception:
            return []

    json_match = re.search(r"\[.*\]", extraction, re.DOTALL)
    if not json_match:
        return []
    try:
        relationships = json.loads(json_match.group())
    except Exception:
        return []

    results = []
    for rel in relationships[:5]:
        if all(k in rel for k in ["entity1", "relationship", "entity2"]):
            e1 = rel["entity1"].strip()
            e2 = rel["entity2"].strip()
            r = rel["relationship"].strip()
            if e1 and e2 and r:
                add_entity(e1, "concept")
                add_entity(e2, "concept")
                add_relationship(e1, r, e2)
                results.append(rel)
    return results


def search_neighbors(entity: str, max_distance: int = 1) -> list[dict]:
    if not _graph.has_node(entity):
        return []
    try:
        if max_distance == 1:
            nodes = set(nx.descendants(_graph, entity)) | set(nx.ancestors(_graph, entity))
        else:
            nodes = set(nx.descendants(_graph, entity)) | set(nx.ancestors(_graph, entity))
            for _ in range(max_distance - 1):
                more = set()
                for n in nodes:
                    more |= set(nx.descendants(_graph, n)) | set(nx.ancestors(_graph, n))
                nodes |= more
    except Exception:
        return []

    results = []
    for neighbor in nodes:
        edge_info = []
        for _, _, data in _graph.out_edges(entity, data=True):
            edge_info.append(data.get("relationship", "related_to"))
        for _, _, data in _graph.in_edges(entity, data=True):
            edge_info.append(data.get("relationship", "related_to"))
        props = {k: v for k, v in _graph.nodes[neighbor].items() if k != "entity_type"}
        results.append({
            "entity": neighbor,
            "entity_type": _graph.nodes[neighbor].get("entity_type", "concept"),
            "relationships": list(set(edge_info)),
            "properties": props,
        })
    return results


def hybrid_graph_search(query: str, top_k: int = 5) -> list[dict]:
    results = []
    q = query.lower()

    for name, data in _graph.nodes(data=True):
        score = 0
        if q in name.lower():
            score += 3
        for k, v in data.items():
            if isinstance(v, str) and q in v.lower():
                score += 1
        for _, _, edge_data in _graph.out_edges(name, data=True):
            rel = edge_data.get("relationship", "")
            if q in rel.lower():
                score += 0.5
        if score > 0:
            neighbors = search_neighbors(name)
            results.append({
                "entity": name,
                "entity_type": data.get("entity_type", "concept"),
                "score": score,
                "neighbors": [n["entity"] for n in neighbors[:5]],
            })

    results.sort(key=lambda x: -x["score"])
    return results[:top_k]


def get_graph_summary() -> str:
    counts = {}
    for _, data in _graph.nodes(data=True):
        kind = data.get("entity_type", "concept")
        counts[kind] = counts.get(kind, 0) + 1
    type_text = ", ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
    return f"{_graph.number_of_nodes()} entities, {_graph.number_of_edges()} relationships" + (
        f" ({type_text})" if type_text else ""
    )


def seed_initial_knowledge():
    if _graph.number_of_nodes() > 0:
        return
    add_entity("Debasish", "person", {"location": "Aurora Illinois", "age": 16})
    add_entity("Jarvis", "project", {"status": "active"})
    add_entity("AquAlert", "project", {"status": "planning"})
    add_entity("BritishWrite", "project", {"status": "active"})
    add_entity("Around Cafe", "project", {"status": "on hold"})
    add_entity("ESP32", "tool", {"arrives": "late summer"})
    add_entity("MacBook Pro", "tool", {"status": "planned purchase"})
    add_relationship("Debasish", "created", "Jarvis")
    add_relationship("Debasish", "created", "AquAlert")
    add_relationship("Debasish", "created", "BritishWrite")
    add_relationship("AquAlert", "uses", "ESP32")
    add_relationship("Debasish", "plans_to_buy", "MacBook Pro")


load_graph()
seed_initial_knowledge()

# extract_entities_relations deliberately NOT in GRAPH_DEFINITIONS
# so models can't call it autonomously. GRAPH_TOOLS keeps the
# runtime function accessible for manual terminal "graph extract" commands.
GRAPH_DEFINITIONS: list = []
GRAPH_TOOLS = {
    "extract_entities_relations": extract_entities_relations
}
