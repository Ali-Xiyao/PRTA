from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "merge_luna_primary_main",
            module_name="prta_cxr.cli_luna_primary",
        )
    )
