from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "state_pruning_compare_main", module_name="prta_cxr.state_pruning_evidence"
        )
    )
