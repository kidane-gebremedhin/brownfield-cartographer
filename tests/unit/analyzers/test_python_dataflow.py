from analyzers.python_dataflow import extract_python_lineage


def test_pandas_read_csv_detected():
    py = "import pandas as pd\ndf = pd.read_csv('s3://bucket/x.csv')"
    r = extract_python_lineage(py)
    assert any(s.ref_type == 'file' and 's3://bucket/x.csv' in s.name for s in r.sources)


def test_dynamic_reference_preserved():
    py = "import pandas as pd\npath = get_path()\ndf = pd.read_csv(path)"
    r = extract_python_lineage(py)
    assert any(s.ref_type == 'unresolved' for s in r.sources)
