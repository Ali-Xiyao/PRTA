from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "merge_and_audit_labels_main", module_name="prta_cxr.cli_labeling"
        )
    )
