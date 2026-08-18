from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "reconcile_slim_offload_main",
            module_name="prta_cxr.slim_offload_reconcile",
        )
    )
