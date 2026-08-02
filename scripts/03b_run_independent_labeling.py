from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "run_independent_ai_main",
            module_name="prta_cxr.cli_independent_silver",
        )
    )
