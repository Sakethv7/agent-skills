"""
notebook-runner MCP server

Tools for reading, editing, and executing Jupyter notebooks programmatically.
Agents can inspect cell content, run cells, get outputs, and export notebooks
without opening Jupyter UI.

Dependencies: nbformat, nbconvert, jupyter_client (pip)
"""

import json
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

import nbformat
from mcp.server.fastmcp import FastMCP
from nbformat.v4 import new_code_cell, new_markdown_cell

mcp = FastMCP(
    "notebook-runner",
    instructions=(
        "Tools for working with Jupyter notebooks. Use get_notebook_info first "
        "to understand the notebook structure before running or editing cells. "
        "run_cell executes a single cell; run_all executes all cells in order. "
        "Always check cell outputs after running — errors appear in outputs, not "
        "as exceptions from the tool itself."
    ),
)


def _load(path: str) -> nbformat.NotebookNode:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"No notebook at {path}")
    if p.suffix not in (".ipynb",):
        raise ValueError(f"Expected .ipynb file, got {p.suffix}")
    return nbformat.read(str(p), as_version=4)


def _save(nb: nbformat.NotebookNode, path: str) -> None:
    nbformat.write(nb, path)


def _cell_summary(cell: nbformat.NotebookNode, idx: int) -> dict:
    outputs = cell.get("outputs", [])
    error = next(
        (o for o in outputs if o.get("output_type") == "error"), None
    )
    return {
        "index": idx,
        "type": cell.cell_type,
        "execution_count": cell.get("execution_count"),
        "source_preview": cell.source[:120].replace("\n", " "),
        "output_count": len(outputs),
        "has_error": error is not None,
        "error_name": error.get("ename") if error else None,
    }


# ---------------------------------------------------------------------------
# Inspection tools
# ---------------------------------------------------------------------------


@mcp.tool()
def get_notebook_info(path: str) -> dict:
    """
    Return metadata about a notebook: kernel, language, cell counts, and
    whether any cells have errors or are unexecuted.

    Args:
        path: Absolute path to the .ipynb file.
    """
    nb = _load(path)
    cells = nb.cells
    code_cells = [c for c in cells if c.cell_type == "code"]
    executed = [c for c in code_cells if c.get("execution_count") is not None]
    errors = [
        c for c in code_cells
        if any(o.get("output_type") == "error" for o in c.get("outputs", []))
    ]
    return {
        "path": path,
        "kernel": nb.metadata.get("kernelspec", {}).get("display_name", "unknown"),
        "language": nb.metadata.get("kernelspec", {}).get("language", "unknown"),
        "total_cells": len(cells),
        "code_cells": len(code_cells),
        "markdown_cells": len([c for c in cells if c.cell_type == "markdown"]),
        "executed_cells": len(executed),
        "unexecuted_cells": len(code_cells) - len(executed),
        "cells_with_errors": len(errors),
        "nbformat": nb.nbformat,
    }


@mcp.tool()
def list_cells(path: str) -> list[dict]:
    """
    List all cells with their index, type, execution count, and a short
    preview of their content. Use this to find which cell index to target
    before calling get_cell or run_cell.

    Args:
        path: Absolute path to the .ipynb file.
    """
    nb = _load(path)
    return [_cell_summary(cell, i) for i, cell in enumerate(nb.cells)]


@mcp.tool()
def get_cell(path: str, index: int) -> dict:
    """
    Get the full source and all outputs of a specific cell.

    Args:
        path: Absolute path to the .ipynb file.
        index: 0-based cell index (use list_cells to find it).
    """
    nb = _load(path)
    if index < 0 or index >= len(nb.cells):
        raise IndexError(f"Cell index {index} out of range (notebook has {len(nb.cells)} cells)")

    cell = nb.cells[index]
    outputs = []
    for o in cell.get("outputs", []):
        otype = o.get("output_type")
        if otype == "stream":
            outputs.append({"type": "stream", "name": o.get("name"), "text": "".join(o.get("text", []))})
        elif otype in ("display_data", "execute_result"):
            data = o.get("data", {})
            outputs.append({
                "type": otype,
                "text": "".join(data.get("text/plain", [])),
                "has_image": "image/png" in data,
            })
        elif otype == "error":
            outputs.append({
                "type": "error",
                "ename": o.get("ename"),
                "evalue": o.get("evalue"),
                "traceback_last": o.get("traceback", [""])[-1] if o.get("traceback") else "",
            })

    return {
        "index": index,
        "type": cell.cell_type,
        "execution_count": cell.get("execution_count"),
        "source": cell.source,
        "outputs": outputs,
    }


@mcp.tool()
def get_errors(path: str) -> list[dict]:
    """
    Return all cells that have error outputs, with their index, source, and
    error details. Use this to quickly find what's broken in a notebook.

    Args:
        path: Absolute path to the .ipynb file.
    """
    nb = _load(path)
    errors = []
    for i, cell in enumerate(nb.cells):
        for o in cell.get("outputs", []):
            if o.get("output_type") == "error":
                errors.append({
                    "cell_index": i,
                    "source_preview": cell.source[:200],
                    "ename": o.get("ename"),
                    "evalue": o.get("evalue"),
                    "traceback": "\n".join(o.get("traceback", [])),
                })
    return errors


# ---------------------------------------------------------------------------
# Execution tools
# ---------------------------------------------------------------------------


@mcp.tool()
def run_cell(path: str, index: int, timeout: int = 60) -> dict:
    """
    Execute a single cell and return its output. The notebook is saved after
    execution with updated outputs and execution count.

    Args:
        path: Absolute path to the .ipynb file.
        index: 0-based cell index to execute.
        timeout: Max seconds to wait for cell execution (default 60).
    """
    try:
        import jupyter_client
        from nbconvert.preprocessors import ExecutePreprocessor
    except ImportError:
        raise RuntimeError("pip install jupyter_client nbconvert")

    nb = _load(path)
    if index < 0 or index >= len(nb.cells):
        raise IndexError(f"Cell index {index} out of range")

    cell = nb.cells[index]
    if cell.cell_type != "code":
        return {"index": index, "skipped": True, "reason": f"Cell is {cell.cell_type}, not code"}

    # Build a single-cell notebook to execute in isolation
    single = nbformat.v4.new_notebook()
    single.cells = [cell]
    single.metadata = nb.metadata

    ep = ExecutePreprocessor(timeout=timeout, kernel_name=nb.metadata.get("kernelspec", {}).get("name", "python3"))
    try:
        ep.preprocess(single, {"metadata": {"path": str(Path(path).parent)}})
        executed_cell = single.cells[0]
        nb.cells[index] = executed_cell
        _save(nb, path)
        return get_cell(path, index)
    except Exception as e:
        return {"index": index, "error": str(e)}


@mcp.tool()
def run_all(path: str, timeout: int = 300) -> dict:
    """
    Execute all cells in the notebook in order. Returns a summary of which
    cells passed and which errored.

    Args:
        path: Absolute path to the .ipynb file.
        timeout: Total timeout in seconds (default 300).
    """
    try:
        from nbconvert.preprocessors import ExecutePreprocessor, CellExecutionError
    except ImportError:
        raise RuntimeError("pip install nbconvert jupyter_client")

    nb = _load(path)
    ep = ExecutePreprocessor(timeout=timeout, kernel_name=nb.metadata.get("kernelspec", {}).get("name", "python3"))

    results = {"total": len(nb.cells), "executed": 0, "errors": [], "skipped": 0}
    try:
        ep.preprocess(nb, {"metadata": {"path": str(Path(path).parent)}})
        results["executed"] = len([c for c in nb.cells if c.cell_type == "code"])
        _save(nb, path)
    except Exception as e:
        results["stopped_at_error"] = str(e)
        _save(nb, path)

    results["errors"] = [
        {"cell_index": i, "ename": o.get("ename"), "evalue": o.get("evalue")}
        for i, cell in enumerate(nb.cells)
        for o in cell.get("outputs", [])
        if o.get("output_type") == "error"
    ]
    return results


@mcp.tool()
def run_range(path: str, start: int, end: int, timeout: int = 120) -> list[dict]:
    """
    Execute cells from start to end (inclusive) in order. Useful for re-running
    a specific section without running the whole notebook.

    Args:
        path: Absolute path to the .ipynb file.
        start: First cell index to execute (0-based).
        end: Last cell index to execute (inclusive).
        timeout: Per-cell timeout in seconds (default 120).
    """
    nb = _load(path)
    results = []
    for i in range(start, min(end + 1, len(nb.cells))):
        cell = nb.cells[i]
        if cell.cell_type != "code":
            results.append({"index": i, "skipped": True, "reason": cell.cell_type})
            continue
        result = run_cell(path, i, timeout)
        results.append(result)
        if result.get("outputs") and any(o.get("type") == "error" for o in result.get("outputs", [])):
            results.append({"stopped": True, "reason": f"Error in cell {i}"})
            break
    return results


# ---------------------------------------------------------------------------
# Editing tools
# ---------------------------------------------------------------------------


@mcp.tool()
def insert_cell(path: str, index: int, source: str, cell_type: str = "code") -> dict:
    """
    Insert a new cell at the given index. Existing cells shift down.

    Args:
        path: Absolute path to the .ipynb file.
        index: Position to insert at (0 = before first cell).
        source: Cell content.
        cell_type: "code" or "markdown" (default "code").
    """
    nb = _load(path)
    if cell_type == "code":
        cell = new_code_cell(source=source)
    elif cell_type == "markdown":
        cell = new_markdown_cell(source=source)
    else:
        raise ValueError(f"cell_type must be 'code' or 'markdown', got '{cell_type}'")

    nb.cells.insert(index, cell)
    _save(nb, path)
    return {"inserted_at": index, "total_cells": len(nb.cells)}


@mcp.tool()
def update_cell(path: str, index: int, source: str) -> dict:
    """
    Replace the source of an existing cell. Does not execute it.

    Args:
        path: Absolute path to the .ipynb file.
        index: 0-based cell index to update.
        source: New cell content.
    """
    nb = _load(path)
    if index < 0 or index >= len(nb.cells):
        raise IndexError(f"Cell {index} out of range")
    nb.cells[index].source = source
    nb.cells[index]["outputs"] = []
    nb.cells[index]["execution_count"] = None
    _save(nb, path)
    return {"updated": index, "source_preview": source[:100]}


@mcp.tool()
def delete_cell(path: str, index: int) -> dict:
    """
    Delete a cell at the given index.

    Args:
        path: Absolute path to the .ipynb file.
        index: 0-based cell index to delete.
    """
    nb = _load(path)
    if index < 0 or index >= len(nb.cells):
        raise IndexError(f"Cell {index} out of range")
    removed = nb.cells.pop(index)
    _save(nb, path)
    return {"deleted_index": index, "deleted_preview": removed.source[:80], "remaining_cells": len(nb.cells)}


@mcp.tool()
def clear_outputs(path: str, index: Optional[int] = None) -> dict:
    """
    Clear outputs from one cell or all cells.

    Args:
        path: Absolute path to the .ipynb file.
        index: Cell to clear. If None, clears all cells.
    """
    nb = _load(path)
    if index is not None:
        nb.cells[index]["outputs"] = []
        nb.cells[index]["execution_count"] = None
        cleared = 1
    else:
        for cell in nb.cells:
            if cell.cell_type == "code":
                cell["outputs"] = []
                cell["execution_count"] = None
        cleared = len([c for c in nb.cells if c.cell_type == "code"])
    _save(nb, path)
    return {"cleared_cells": cleared}


# ---------------------------------------------------------------------------
# Export tools
# ---------------------------------------------------------------------------


@mcp.tool()
def export_to_script(path: str, output_path: Optional[str] = None) -> dict:
    """
    Convert a notebook to a .py script. Markdown cells become comments.
    Useful for running notebooks as standalone scripts or putting them in CI.

    Args:
        path: Absolute path to the .ipynb file.
        output_path: Where to write the .py file. Defaults to same dir as notebook.
    """
    try:
        from nbconvert import PythonExporter
    except ImportError:
        raise RuntimeError("pip install nbconvert")

    nb = _load(path)
    exporter = PythonExporter()
    script, _ = exporter.from_notebook_node(nb)

    if output_path is None:
        output_path = str(Path(path).with_suffix(".py"))

    Path(output_path).write_text(script)
    return {"output_path": output_path, "size_bytes": len(script.encode())}


@mcp.tool()
def get_variables(path: str, timeout: int = 30) -> dict:
    """
    Run a introspection cell to get the current variable state of a notebook
    that has already been executed. Returns variable names, types, and shapes
    (for numpy arrays and pandas DataFrames).

    Args:
        path: Absolute path to the .ipynb file.
        timeout: Execution timeout in seconds.
    """
    introspect_source = """
import json, sys
_out = {}
for _name, _val in list(globals().items()):
    if _name.startswith('_'): continue
    try:
        _type = type(_val).__name__
        _info = {"type": _type}
        if hasattr(_val, 'shape'): _info["shape"] = list(_val.shape)
        if hasattr(_val, '__len__') and not isinstance(_val, str): _info["len"] = len(_val)
        _out[_name] = _info
    except Exception:
        pass
print(json.dumps(_out))
""".strip()

    nb = _load(path)
    # Append a temp cell, run it, read output, remove it
    tmp_idx = len(nb.cells)
    nb.cells.append(new_code_cell(source=introspect_source))
    _save(nb, path)

    try:
        result = run_cell(path, tmp_idx, timeout)
        # Remove the temp cell
        nb2 = _load(path)
        nb2.cells.pop(tmp_idx)
        _save(nb2, path)

        text_output = next(
            (o.get("text", "") for o in result.get("outputs", []) if o.get("type") == "stream"),
            "{}"
        )
        return {"variables": json.loads(text_output)}
    except Exception as e:
        # Always clean up
        nb2 = _load(path)
        if len(nb2.cells) > tmp_idx:
            nb2.cells.pop(tmp_idx)
            _save(nb2, path)
        return {"error": str(e)}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
