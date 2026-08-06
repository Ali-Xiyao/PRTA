from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "analyze_minimum_wave_dev_main",
            module_name="prta_cxr.minimum_wave",
        )
    )
