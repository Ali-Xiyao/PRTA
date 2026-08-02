from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "build_training_store_main",
            module_name="prta_cxr.cli_training_store",
        )
    )
