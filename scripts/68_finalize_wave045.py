from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "wave045_finalization_main",
            module_name="prta_cxr.wave045_finalization",
        )
    )
