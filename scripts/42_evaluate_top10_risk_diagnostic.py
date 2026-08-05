from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "evaluate_risk_filter_diagnostic_main",
            module_name="prta_cxr.risk_filter_diagnostic",
        )
    )
