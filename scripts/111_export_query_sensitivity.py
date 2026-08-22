from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "query_sensitivity_export_main",
            module_name="prta_cxr.query_sensitivity",
        )
    )
