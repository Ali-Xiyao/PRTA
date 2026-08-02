from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "derive_silver_quality_gate_main", module_name="prta_cxr.cli_protocol"
        )
    )
