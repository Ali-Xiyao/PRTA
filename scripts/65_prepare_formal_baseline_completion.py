from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "prepare_formal_baseline_completion_main",
            module_name="prta_cxr.formal_baseline_completion",
        )
    )
