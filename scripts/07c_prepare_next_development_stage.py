from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "prepare_next_development_stage_main",
            module_name="prta_cxr.cli_development_selection",
        )
    )
