from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "prepare_independent_pilot_main",
            module_name="prta_cxr.cli_independent_silver",
        )
    )
