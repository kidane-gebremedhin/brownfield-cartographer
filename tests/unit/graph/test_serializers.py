import json

import networkx as nx

from graph.serializers import serialize_digraph


def test_serialize_digraph_stable_ordering():
    g = nx.DiGraph()
    g.add_node('b', z=1)
    g.add_node('a', z=2)
    g.add_edge('b', 'a', weight=3)

    s = serialize_digraph(g)
    assert [n['id'] for n in s['nodes']] == ['a', 'b']
    assert s['edges'][0]['source'] == 'b'
    assert s['edges'][0]['target'] == 'a'

    # JSON round-trip
    payload = json.dumps(s, sort_keys=True)
    s2 = json.loads(payload)
    assert s2["directed"] is True


def test_serialize_digraph_preserves_node_attrs():
    g = nx.DiGraph()
    g.add_node("n1", node_type="dataset", count=42)
    g.add_edge("n1", "n2", edge_type="produces")
    s = serialize_digraph(g)
    n1 = next(x for x in s["nodes"] if x["id"] == "n1")
    assert n1["attrs"].get("node_type") == "dataset"
    assert n1["attrs"].get("count") == 42
    e = next(x for x in s["edges"] if x["source"] == "n1" and x["target"] == "n2")
    assert e["attrs"].get("edge_type") == "produces"
