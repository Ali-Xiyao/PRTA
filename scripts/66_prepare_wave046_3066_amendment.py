from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "prepare_wave046_3066_amendment_main",
            module_name="prta_cxr.wave046_amendment",
        )
    )
