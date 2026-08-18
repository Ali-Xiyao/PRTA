from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "prepare_rexgradient_external_main",
            module_name="prta_cxr.rexgradient_external",
        )
    )
