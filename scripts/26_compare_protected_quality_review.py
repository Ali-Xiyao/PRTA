from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "compare_protected_quality_main",
            module_name="prta_cxr.protected_quality_review",
        )
    )
