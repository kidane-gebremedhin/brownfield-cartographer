# Repository Ingestion Spec

## Objective
Safely load repositories from a local path or GitHub URL.

## Files This Spec Owns
- `src/repository/loader.py`
- `src/repository/git_tools.py`
- `src/repository/file_discovery.py`
- `src/utils/safe_subprocess.py`
- related tests

## Requirements
- clone remote repos into temporary directories only
- never clone into the live working directory
- use subprocess safely with explicit argument lists
- support local path input
- support branch/ref override
- discover supported file types
- compute stable content hashes for incremental mode

## Supported File Types
- `.py`
- `.sql`
- `.yaml`
- `.yml`
- `.json`
- `.md`
- `.ipynb`

## Acceptance Criteria
- local path loading works
- GitHub cloning works
- unsupported files are filtered
- errors are logged clearly
- content hashes are stable