from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "finalize_wave046_wave047_main",
            module_name="prta_cxr.wave046_047_finalization",
        )
    )
