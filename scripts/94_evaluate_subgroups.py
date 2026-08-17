from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch("subgroup_evidence_main", module_name="prta_cxr.subgroup_evidence")
    )
