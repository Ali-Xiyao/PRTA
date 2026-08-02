from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "prepare_gold_cache_input_main",
            module_name="prta_cxr.cli_protocol",
        )
    )
