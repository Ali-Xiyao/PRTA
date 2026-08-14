from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "regress_ifusion_v2_main",
            module_name="prta_cxr.ifusion_regression",
        )
    )
