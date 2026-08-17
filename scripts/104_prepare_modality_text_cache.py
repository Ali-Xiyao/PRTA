from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "prepare_modality_text_cache_main", module_name="prta_cxr.modality_assets"
        )
    )
