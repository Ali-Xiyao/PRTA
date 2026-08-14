from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "prepare_confirmation_main",
            module_name="prta_cxr.wave047_confirmation",
        )
    )
