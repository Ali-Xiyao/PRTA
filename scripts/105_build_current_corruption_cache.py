from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "build_current_corruption_cache_main",
            module_name="prta_cxr.modality_assets",
        )
    )
