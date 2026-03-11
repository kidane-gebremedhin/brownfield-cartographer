import json
from dataclasses import dataclass
from pathlib import Path

import networkx as nx

from agents.archivist import ArchivistInputs, write_artifacts


@dataclass(frozen=True)
class FakeSurveyor:
    graph: nx.DiGraph
    modules: dict


@dataclass(frozen=True)
class FakeHydrologist:
    graph: nx.DiGraph


def test_archivist_writes_all_artifacts(tmp_path):
    mg = nx.DiGraph()
    mg.add_node('a.py')
    mg.add_node('b.py')
    mg.add_edge('a.py', 'b.py')

    lg = nx.DiGraph()
    lg.add_node('raw.users', node_type='dataset')
    lg.add_node('sql:model.sql', node_type='transformation')
    lg.add_edge('raw.users', 'sql:model.sql', edge_type='consumes')

    surveyor = FakeSurveyor(graph=mg, modules={})
    hydro = FakeHydrologist(graph=lg)

    out = write_artifacts(ArchivistInputs(repo_root=tmp_path, surveyor_result=surveyor, hydrologist_result=hydro), out_dir=tmp_path / '.cartography')

    assert (out / 'CODEBASE.md').exists()
    assert (out / 'onboarding_brief.md').exists()
    assert (out / 'module_graph.json').exists()
    assert (out / 'lineage_graph.json').exists()
    assert (out / 'cartography_trace.jsonl').exists()

    codebase = (out / 'CODEBASE.md').read_text(encoding='utf-8')
    assert '## Architecture Overview' in codebase
    assert '## Critical Path' in codebase
    assert '## Data Sources & Sinks' in codebase
    assert '## Known Debt' in codebase
    assert 'High-Velocity' in codebase or 'Recent Change Velocity' in codebase
    assert '## Module Purpose Index' in codebase

    onboarding = (out / 'onboarding_brief.md').read_text(encoding='utf-8')
    assert '## Day-One Answers' in onboarding
    assert '## Evidence citations' in onboarding
    assert '## Confidence notes' in onboarding
    assert '## Known unknowns' in onboarding

    mod_json = json.loads((out / 'module_graph.json').read_text(encoding='utf-8'))
    assert mod_json['directed'] is True
    assert any(n['id'] == 'a.py' for n in mod_json['nodes'])

    # Pyvis HTML when available
    if (out / 'module_graph.html').exists():
        assert (out / 'lineage_graph.html').exists()
        assert 'a.py' in (out / 'module_graph.html').read_text(encoding='utf-8')


def test_archivist_trace_jsonl_deterministic(tmp_path):
    mg = nx.DiGraph()
    lg = nx.DiGraph()
    surveyor = FakeSurveyor(graph=mg, modules={})
    hydro = FakeHydrologist(graph=lg)

    events = [
        {"event": "analysis_start", "i": 2},
        {"event": "analysis_end", "i": 1},
    ]

    out = write_artifacts(
        ArchivistInputs(repo_root=tmp_path, surveyor_result=surveyor, hydrologist_result=hydro, trace_events=events),
        out_dir=tmp_path / '.cartography',
    )

    lines = (out / 'cartography_trace.jsonl').read_text(encoding='utf-8').splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])['event'] == 'analysis_start'
    assert json.loads(lines[1])['event'] == 'analysis_end'
