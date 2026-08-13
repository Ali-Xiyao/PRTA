from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "diagnostic_main",
            module_name="prta_cxr.prta_v2_diagnostics",
        )
    )
