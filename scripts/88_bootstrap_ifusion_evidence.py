from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "ifusion_bootstrap_main",
            module_name="prta_cxr.ifusion_bootstrap",
        )
    )
