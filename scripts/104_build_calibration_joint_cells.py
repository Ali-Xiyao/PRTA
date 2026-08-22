from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch("evidence_cells_main", module_name="prta_cxr.evidence_cells")
    )
